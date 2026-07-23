from sqlalchemy import select

from scriptflow_v7.novel.contracts import NovelBlock
from scriptflow_v7.novel.domain import (
    NovelBlueprintAnchorModel,
    NovelBlueprintModel,
    NovelDocumentRevisionModel,
    NovelRevisionStatus,
)
from scriptflow_v7.novel.service import NovelService
from scriptflow_v7.review.domain import FindingDomain, FindingDraft, FindingSeverity
from scriptflow_v7.review.service import ReviewDomainAdapter, ReviewService


def create_novel_review_service(database) -> ReviewService:
    return ReviewService(
        database,
        ReviewDomainAdapter(
            medium="novel",
            revision_model=NovelDocumentRevisionModel,
            unit_field="chapter_id",
            element_field="block_id",
            adopted_status=NovelRevisionStatus.ADOPTED,
            candidate_status=NovelRevisionStatus.CANDIDATE,
            superseded_status=NovelRevisionStatus.SUPERSEDED,
            anchor_model=NovelBlueprintAnchorModel,
            anchor_blueprint_field="blueprint_id",
            anchor_key_field="anchor_key",
            blueprint_model=NovelBlueprintModel,
            block_model=NovelBlock,
            validate_blocks=NovelService._validate_blocks,
        ),
    )


async def novel_scan_input(database, project_id: str, chapter_id: str):
    async with database.session() as session:
        revision = (
            await session.scalars(
                select(NovelDocumentRevisionModel).where(
                    NovelDocumentRevisionModel.project_id == project_id,
                    NovelDocumentRevisionModel.chapter_id == chapter_id,
                    NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                )
            )
        ).one_or_none()
        blueprint = (
            await session.scalars(
                select(NovelBlueprintModel).where(
                    NovelBlueprintModel.project_id == project_id,
                    NovelBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        if revision is None or blueprint is None:
            raise RuntimeError("adopted Novel document and blueprint are required")
        anchor = (
            await session.scalars(
                select(NovelBlueprintAnchorModel)
                .where(NovelBlueprintAnchorModel.blueprint_id == blueprint.id)
                .order_by(NovelBlueprintAnchorModel.kind)
            )
        ).first()
        block = next(
            (item for item in revision.blocks if item["type"] == "prose"), revision.blocks[0]
        )
        text = str(block["text"])
        replacement = dict(block)
        replacement["text"] = f"{text} 她没有立即触碰它，先听见了自己紊乱的呼吸。"
        return revision.id, FindingDraft(
            domain=FindingDomain.CHARACTER,
            severity=FindingSeverity.MAJOR,
            anchor_type=anchor.kind,
            anchor_id=anchor.anchor_key,
            anchor_note="内心活动与叙述视角",
            element_id=str(block["block_id"]),
            original_excerpt=text[:60],
            locator={"element_id": block["block_id"], "start": 0, "end": len(text)},
            diagnosis="人物的内在反应弱于事件带来的情绪压力。",
            suggestion="增加身体感受与迟疑。",
            suggested_patch={
                "base_revision_id": revision.id,
                "block_id": block["block_id"],
                "expected_text": text,
                "replacement": [replacement],
            },
            confidence="high",
        )
