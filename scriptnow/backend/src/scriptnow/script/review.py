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
