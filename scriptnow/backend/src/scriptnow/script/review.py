import json

from sqlalchemy import select

from scriptnow.review.domain import FindingDomain, FindingDraft, FindingSeverity
from scriptnow.review.service import ReviewDomainAdapter, ReviewService
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import (
    RevisionStatus,
    ScriptBlueprintAnchorModel,
    ScriptBlueprintModel,
    ScriptDocumentRevisionModel,
)
from scriptnow.script.service import ScriptService


def create_script_review_service(database) -> ReviewService:
    return ReviewService(
        database,
        ReviewDomainAdapter(
            medium="script",
            revision_model=ScriptDocumentRevisionModel,
            unit_field="scene_id",
            element_field="para_id",
            adopted_status=RevisionStatus.ADOPTED,
            candidate_status=RevisionStatus.CANDIDATE,
            superseded_status=RevisionStatus.SUPERSEDED,
            anchor_model=ScriptBlueprintAnchorModel,
            anchor_blueprint_field="blueprint_id",
            anchor_key_field="anchor_key",
            blueprint_model=ScriptBlueprintModel,
            block_model=ScriptBlock,
            validate_blocks=ScriptService._validate_blocks,
        ),
    )


async def script_ai_review_scene(
    database,
    runtime,
    *,
    tenant_id: str,
    project_id: str,
    scene_id: str,
    run_id: str,
) -> int:
    """Run a real AI quality review of an adopted scene and persist findings.

    Replaces the canned placeholder scan: the reviewer agent applies the script
    review rubric (dramatic turn, dialogue seven dimensions) and, when the
    roundtable skill is mounted, the four-perspective doctor framework. Findings
    are anchored to concrete scene blocks and stored through the review service.
    """
    from json_repair import loads as repair_json

    from scriptnow.review.domain import (
        FindingDomain,
        FindingDraft,
        FindingSeverity,
        FindingSource,
    )
    from scriptnow.script.domain import (
        RevisionStatus,
        ScriptBlueprintAnchorModel,
        ScriptBlueprintModel,
        ScriptDocumentRevisionModel,
    )

    async with database.session() as session:
        revision = (
            await session.scalars(
                select(ScriptDocumentRevisionModel).where(
                    ScriptDocumentRevisionModel.project_id == project_id,
                    ScriptDocumentRevisionModel.scene_id == scene_id,
                    ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                )
            )
        ).one_or_none()
        blueprint = (
            await session.scalars(
                select(ScriptBlueprintModel).where(
                    ScriptBlueprintModel.project_id == project_id,
                    ScriptBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        if revision is None or blueprint is None:
            raise RuntimeError("adopted Script document and blueprint are required")
        anchor = (
            await session.scalars(
                select(ScriptBlueprintAnchorModel)
                .where(ScriptBlueprintAnchorModel.blueprint_id == blueprint.id)
                .order_by(ScriptBlueprintAnchorModel.kind)
            )
        ).first()
        blocks = list(revision.blocks)
        anchor_lines = [
            f"- {item.kind}: {item.name}"
            for item in (
                await session.scalars(
                    select(ScriptBlueprintAnchorModel)
                    .where(ScriptBlueprintAnchorModel.blueprint_id == blueprint.id)
                    .order_by(ScriptBlueprintAnchorModel.kind)
                )
            ).all()[:12]
        ]

    scene_text = "\n".join(
        f"[{block.get('para_id')}] ({block.get('type')}) {block.get('text', '')}"
        for block in blocks
    )
    prompt = (
        "你是剧本审读编辑。请对以下已采纳剧本场次做质量审核，输出结构化 finding 清单。\n"
        "审核要求：\n"
        "1. 按台词七维检查对白：角色辨识度、潜台词、冲突推进、类型语感、信息效率、节奏、金句潜力。\n"
        "2. 检查场次功能：删掉本场是否改变因果/关系/信息边界；是否发生可观察转折（目标/权力/关系/知识/风险至少一项改变）。\n"
        "3. 若为竖屏短剧格式，检查交付规范：▲仅用于关键分镜（特写/闪回/动作节拍）且使用要一致、出场人物齐全、"
        "对白为自然完整的一句（同一人物一段完整台词一条 dialogue，长度不限，禁止电报式碎片）、OS/VO克制、特写/闪回标记。\n"
        "4. 每个 finding 必须引用具体段落的 para_id 和原文片段；禁止无证据的空泛评价；没有问题的维度不要硬造 finding。\n"
        "只返回 JSON："
        '{"findings":[{"domain":"worldview|character|arc|event|foreshadow",'
        '"severity":"blocker|major|minor","element_id":"para_id","excerpt":"原文片段",'
        '"diagnosis":"问题诊断","suggestion":"最小修复建议","confidence":"high|mid|low"}],'
        '"summary":"一句话总评"}\n'
        "域映射：对白/角色问题归 character；格式/类型语感归 worldview；连续性/情节推进归 arc 或 event；伏笔归 foreshadow。\n\n"
        f"蓝图锚点：\n{chr(10).join(anchor_lines)}\n\n"
        f"场景内容：\n{scene_text}"
    )
    result = await runtime.generate(
        tenant_id=tenant_id,
        run_id=run_id,
        role="reviewer",
        content=prompt,
        context_snapshot={
            "project_id": project_id,
            "scene_id": scene_id,
            "operation": "script_quality_review",
        },
        stage_override="review",
        explicit_skill_keys=("script-review", "script-doctor-roundtable"),
    )
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError:
        payload = repair_json(result.text)
    if not isinstance(payload, dict):
        raise RuntimeError("script quality review did not return an object")

    service = create_script_review_service(database)
    by_id = {str(block.get("para_id")): block for block in blocks}
    persisted = 0
    for item in (payload.get("findings") or [])[:12]:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("element_id") or "")
        block = by_id.get(element_id)
        if block is None:
            continue
        excerpt = str(item.get("excerpt") or "")
        if excerpt and excerpt not in str(block.get("text", "")):
            continue
        try:
            domain = FindingDomain(str(item.get("domain") or "arc"))
        except ValueError:
            domain = FindingDomain.ARC
        try:
            raw_severity = str(item.get("severity") or "minor").lower()
            if raw_severity in {"blocking", "block", "critical"}:
                raw_severity = "blocker"
            severity = FindingSeverity(raw_severity)
        except ValueError:
            severity = FindingSeverity.MINOR
        draft = FindingDraft(
            domain=domain,
            severity=severity,
            anchor_type=str(anchor.kind) if anchor is not None else "event",
            anchor_id=str(anchor.anchor_key) if anchor is not None else "event:unpinned",
            element_id=element_id,
            original_excerpt=excerpt or str(block.get("text", ""))[:60],
            locator={"element_id": element_id, "start": 0, "end": len(excerpt)},
            diagnosis=str(item.get("diagnosis") or "待补充诊断"),
            suggestion=str(item.get("suggestion") or "待补充修复建议"),
            suggested_patch={},
            confidence=str(item.get("confidence") or "mid"),
        )
        await service.create(
            tenant_id=tenant_id,
            project_id=project_id,
            unit_id=scene_id,
            base_revision_id=revision.id,
            draft=draft,
            source=FindingSource.AI,
            author="Script Editor",
            idempotency_key=f"auto-quality:{scene_id}:{revision.id}:{element_id}",
        )
        persisted += 1
    return result


async def script_scan_input(database, project_id: str, scene_id: str):
    async with database.session() as session:
        revision = (
            await session.scalars(
                select(ScriptDocumentRevisionModel).where(
                    ScriptDocumentRevisionModel.project_id == project_id,
                    ScriptDocumentRevisionModel.scene_id == scene_id,
                    ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                )
            )
        ).one_or_none()
        blueprint = (
            await session.scalars(
                select(ScriptBlueprintModel).where(
                    ScriptBlueprintModel.project_id == project_id,
                    ScriptBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        if revision is None or blueprint is None:
            raise RuntimeError("adopted Script document and blueprint are required")
        anchor = (
            await session.scalars(
                select(ScriptBlueprintAnchorModel)
                .where(ScriptBlueprintAnchorModel.blueprint_id == blueprint.id)
                .order_by(ScriptBlueprintAnchorModel.kind)
            )
        ).first()
        block = next(
            (item for item in revision.blocks if item["type"] == "action"), revision.blocks[0]
        )
        text = str(block["text"])
        replacement = dict(block)
        replacement["text"] = f"{text.rstrip('。')}，但动作暴露出他正在隐瞒真相。"
        return revision.id, FindingDraft(
            domain=FindingDomain.CHARACTER,
            severity=FindingSeverity.MAJOR,
            anchor_type=anchor.kind,
            anchor_id=anchor.anchor_key,
            anchor_note="场景行为一致性",
            element_id=str(block["para_id"]),
            original_excerpt=text[:60],
            locator={"element_id": block["para_id"], "start": 0, "end": len(text)},
            diagnosis="人物动作尚未体现蓝图中的内在压力。",
            suggestion="增加一个泄露心理状态的动作。",
            suggested_patch={
                "base_revision_id": revision.id,
                "para_id": block["para_id"],
                "expected_text": text,
                "replacement": [replacement],
            },
            confidence="high",
        )
