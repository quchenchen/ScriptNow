import pytest
from sqlalchemy import select

from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.domain import (
    NovelBlueprintAnchorDraft,
    NovelBlueprintDraft,
    NovelCandidateStatus,
    NovelDocumentRevisionModel,
    NovelStoryCoreCandidateModel,
    NovelStoryCoreDraft,
)
from scriptnow.novel.project import initialize_novel_project
from scriptnow.novel.review import create_novel_review_service
from scriptnow.novel.service import NovelConflict, NovelDomainError, NovelService
from scriptnow.novel.story_map import Chapter, NovelStoryBeat, Volume
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectEventModel,
    ProjectMedium,
    ProjectModel,
    TenantModel,
)
from scriptnow.review.domain import FindingDomain, FindingDraft, FindingSeverity, FindingSource
from scriptnow.review.service import ReviewConflict, ReviewError


def core_drafts(prefix: str = "Novel") -> tuple[NovelStoryCoreDraft, ...]:
    return tuple(
        NovelStoryCoreDraft(
            title=f"{prefix} {index}",
            premise=f"A sufficiently detailed novel premise for candidate number {index}.",
            point_of_view="limited third person",
            narrative_constraints=("interiority before exposition", "no screenplay directions"),
            angles=("voice", "desire", "relationship", "world", "transformation"),
        )
        for index in range(1, 4)
    )


@pytest.fixture
async def novel_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Novel Studio")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Letters",
            medium=ProjectMedium.NOVEL,
            direction={"structure": "three_act", "point_of_view": "limited third person"},
        )
        session.add(project)
        await session.flush()
        await initialize_novel_project(session, project)
    yield NovelService(database), database, tenant, other, project
    await database.dispose()


async def adopt_core_blueprint(service, tenant, project) -> None:
    cores = await service.generate_story_cores(
        tenant_id=tenant.id,
        project_id=project.id,
        drafts=core_drafts(),
        idempotency_key="core",
    )
    await service.adopt_story_core(
        tenant_id=tenant.id, project_id=project.id, candidate_id=cores[0].id
    )
    candidate = await service.propose_blueprint(
        tenant_id=tenant.id,
        project_id=project.id,
        idempotency_key="blueprint",
        draft=NovelBlueprintDraft(
            anchors=(
                NovelBlueprintAnchorDraft(id="character:mei", kind="character", name="Mei"),
                NovelBlueprintAnchorDraft(id="theme:memory", kind="theme", name="Memory"),
                NovelBlueprintAnchorDraft(id="thread:letter", kind="thread", name="The letter"),
            )
        ),
    )
    await service.adopt_blueprint(
        tenant_id=tenant.id, project_id=project.id, candidate_id=candidate.id
    )


def volumes() -> tuple[Volume, ...]:
    return (
        Volume(
            id="volume-1",
            ordinal=1,
            title="The Return",
            chapters=(
                Chapter(
                    id="chapter-1",
                    ordinal=1,
                    title="Postmark",
                    target_words=3000,
                    point_of_view="Mei",
                    beats=(
                        NovelStoryBeat(
                            id="beat-1",
                            objective="Mei receives the letter.",
                            anchor_ids=("character:mei", "thread:letter"),
                        ),
                    ),
                ),
                Chapter(
                    id="chapter-2",
                    ordinal=2,
                    title="The Dream",
                    target_words=3500,
                    point_of_view="Mei",
                    beats=(
                        NovelStoryBeat(
                            id="beat-2",
                            objective="Memory contradicts the letter.",
                            anchor_ids=("theme:memory",),
                        ),
                    ),
                ),
            ),
        ),
    )


def blocks(text: str = "雨落在没有寄件人的信封上。") -> tuple[NovelBlock, ...]:
    return (
        NovelBlock(block_id="b1", type="heading", text="第一章 邮戳"),
        NovelBlock(block_id="b2", type="prose", text=text),
        NovelBlock(block_id="b3", type="dialogue", text="“我见过这封信。”"),
        NovelBlock(block_id="b4", type="quote", text="记忆是另一种邮差。"),
        NovelBlock(block_id="b5", type="divider", text=""),
    )


@pytest.mark.asyncio
async def test_novel_story_core_revision_idempotency_and_single_adoption(novel_data) -> None:
    service, database, tenant, _, project = novel_data
    first = await service.generate_story_cores(
        tenant_id=tenant.id,
        project_id=project.id,
        drafts=core_drafts("First"),
        idempotency_key="first",
    )
    replay = await service.generate_story_cores(
        tenant_id=tenant.id,
        project_id=project.id,
        drafts=core_drafts("Ignored"),
        idempotency_key="first",
    )
    assert [item.id for item in replay] == [item.id for item in first]
    revised = await service.generate_story_cores(
        tenant_id=tenant.id,
        project_id=project.id,
        drafts=core_drafts("Revised"),
        idempotency_key="second",
        revision_feedback="Strengthen interior voice.",
    )
    await service.adopt_story_core(
        tenant_id=tenant.id, project_id=project.id, candidate_id=revised[2].id
    )
    with pytest.raises(NovelConflict, match="locks"):
        await service.generate_story_cores(
            tenant_id=tenant.id, project_id=project.id, drafts=core_drafts("Late")
        )
    async with database.session() as session:
        records = list(
            await session.scalars(
                select(NovelStoryCoreCandidateModel).order_by(
                    NovelStoryCoreCandidateModel.generation,
                    NovelStoryCoreCandidateModel.ordinal,
                )
            )
        )
        assert len(records) == 6
        assert all(item.status == NovelCandidateStatus.EXPIRED for item in records[:3])
        assert [item.status for item in records[3:]] == ["expired", "expired", "adopted"]


@pytest.mark.asyncio
async def test_novel_blueprint_volume_chapter_impact_and_anchor_validation(novel_data) -> None:
    service, _, tenant, _, project = novel_data
    await adopt_core_blueprint(service, tenant, project)
    candidate = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        volumes=volumes(),
        idempotency_key="structure",
    )
    assert candidate.impact == {"added_units": 5, "removed_units": 0, "retained_units": 0}
    story_map = await service.adopt_structure(
        tenant_id=tenant.id, project_id=project.id, candidate_id=candidate.id
    )
    assert story_map.version == 2
    assert "duration_seconds_target" not in story_map.volumes[0]["chapters"][0]
    bad_chapter = (
        volumes()[0]
        .chapters[0]
        .model_copy(
            update={
                "beats": (NovelStoryBeat(id="bad", objective="Bad", anchor_ids=("script:scene",)),)
            }
        )
    )
    bad_volume = volumes()[0].model_copy(update={"chapters": (bad_chapter,)})
    with pytest.raises(NovelDomainError, match="unknown blueprint"):
        await service.propose_structure(
            tenant_id=tenant.id,
            project_id=project.id,
            expected_version=2,
            volumes=(bad_volume,),
            idempotency_key="bad",
        )


@pytest.mark.asyncio
async def test_novel_writer_versions_word_contract_context_and_decision_events(novel_data) -> None:
    service, database, tenant, other, project = novel_data
    await adopt_core_blueprint(service, tenant, project)
    structure = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        volumes=volumes(),
        idempotency_key="structure",
    )
    await service.adopt_structure(
        tenant_id=tenant.id, project_id=project.id, candidate_id=structure.id
    )
    with pytest.raises(NovelDomainError, match="heading"):
        await service.propose_document(
            tenant_id=tenant.id,
            project_id=project.id,
            chapter_id="chapter-1",
            blocks=(NovelBlock(block_id="x", type="prose", text="No heading"),),
            idempotency_key="invalid",
        )
    first = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        blocks=blocks(),
        idempotency_key="chapter-1-v1",
    )
    human = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        blocks=blocks("她在保存前亲手改写了这一句。"),
        idempotency_key="chapter-1-human-v2",
        parent_revision_id=first.id,
        source="human",
    )
    assert human.parent_revision_id == first.id
    assert human.source == "human"
    assert human.revision_number == 2
    await service.adopt_document(tenant_id=tenant.id, project_id=project.id, revision_id=first.id)
    continuity = await service.context_pack(
        tenant_id=tenant.id, project_id=project.id, chapter_id="chapter-2"
    )
    assert continuity["effective_chapters"] == [
        {
            "chapter_id": "chapter-1",
            "revision_id": human.id,
            "revision_number": 2,
            "source": "human",
            "status": "candidate",
            "blocks": human.blocks,
        }
    ]
    chapter_two = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-2",
        blocks=blocks("梦里，邮戳上的日期缓慢融化。"),
        idempotency_key="chapter-2-v1",
    )
    await service.adopt_document(
        tenant_id=tenant.id, project_id=project.id, revision_id=chapter_two.id
    )
    competing_one = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        blocks=blocks("她烧掉了信。"),
        idempotency_key="chapter-1-v2",
    )
    competing_two = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        blocks=blocks("她藏起了信。"),
        idempotency_key="chapter-1-v3",
    )
    await service.adopt_document(
        tenant_id=tenant.id, project_id=project.id, revision_id=competing_one.id
    )
    with pytest.raises(NovelConflict, match="stale"):
        await service.adopt_document(
            tenant_id=tenant.id, project_id=project.id, revision_id=competing_two.id
        )
    pack = await service.context_pack(
        tenant_id=tenant.id, project_id=project.id, chapter_id="chapter-2"
    )
    assert len(pack["adopted_chapters"]) == 2
    assert {item["kind"] for item in pack["anchors"]} == {"character", "theme", "thread"}
    with pytest.raises(NovelDomainError, match="tenant scope"):
        await service.context_pack(
            tenant_id=other.id, project_id=project.id, chapter_id="chapter-1"
        )
    async with database.session() as session:
        events = list(
            await session.scalars(
                select(ProjectEventModel)
                .where(ProjectEventModel.stream_key == f"project:{project.id}")
                .order_by(ProjectEventModel.sequence)
            )
        )
        assert [item.payload["action"] for item in events] == [
            "novel_story_core.propose",
            "novel_story_core.adopt",
            "novel_blueprint.propose",
            "novel_blueprint.adopt",
            "novel_story_map.propose",
            "novel_story_map.adopt",
            "novel_document.adopt",
            "novel_document.adopt",
            "novel_document.adopt",
        ]
        proposed = events[0]
        assert proposed.event_type == "conversation"
        assert proposed.actor == {"type": "agent", "role": "director"}
        assert [item["title"] for item in proposed.payload["candidates"]] == [
            "Novel 1",
            "Novel 2",
            "Novel 3",
        ]
        adopted = events[1]
        assert adopted.actor == {"type": "user"}
        assert adopted.payload["candidate"]["title"] == "Novel 1"
        adopted = list(
            await session.scalars(
                select(NovelDocumentRevisionModel).where(
                    NovelDocumentRevisionModel.status == "adopted"
                )
            )
        )
        assert {item.chapter_id for item in adopted} == {"chapter-1", "chapter-2"}


def test_novel_contract_has_no_script_fields() -> None:
    schema = NovelStoryCoreDraft.model_json_schema()["properties"]
    assert "script_format" not in schema
    assert "duration_seconds" not in schema
    with pytest.raises(NovelDomainError, match="empty text"):
        NovelService._validate_blocks(
            (
                NovelBlock(block_id="h", type="heading", text="Heading"),
                NovelBlock(block_id="d", type="divider", text="CUT TO"),
            )
        )


@pytest.mark.asyncio
async def test_novel_finding_accept_and_stale_guard(novel_data) -> None:
    service, database, tenant, _, project = novel_data
    await adopt_core_blueprint(service, tenant, project)
    structure = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        volumes=volumes(),
        idempotency_key="review-structure",
    )
    await service.adopt_structure(
        tenant_id=tenant.id, project_id=project.id, candidate_id=structure.id
    )
    document = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        blocks=blocks(),
        idempotency_key="review-document",
    )
    await service.adopt_document(
        tenant_id=tenant.id, project_id=project.id, revision_id=document.id
    )
    review = create_novel_review_service(database)
    draft = FindingDraft(
        domain=FindingDomain.CHARACTER,
        severity=FindingSeverity.MAJOR,
        anchor_type="character",
        anchor_id="character:mei",
        element_id="b2",
        original_excerpt="信封",
        diagnosis="人物反应过于直接。",
        suggestion="增加迟疑与身体感受。",
        suggested_patch={
            "expected_text": blocks()[1].text,
            "replacement": [
                {
                    "block_id": "b2-r",
                    "type": "prose",
                    "text": "她的手停在旧信上方，迟迟没有落下。",
                }
            ],
        },
        confidence="high",
    )
    with pytest.raises(ReviewError, match="unknown anchor"):
        await review.create(
            tenant_id=tenant.id,
            project_id=project.id,
            unit_id="chapter-1",
            base_revision_id=document.id,
            draft=draft.model_copy(update={"anchor_id": "missing"}),
            source=FindingSource.AI,
            author="Novel Editor",
            idempotency_key="invalid-anchor",
        )
    finding = await review.create(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id="chapter-1",
        base_revision_id=document.id,
        draft=draft,
        source=FindingSource.AI,
        author="Novel Editor",
        idempotency_key="finding-1",
    )
    accepted = await review.accept(
        tenant_id=tenant.id, project_id=project.id, finding_id=finding.id
    )
    assert accepted.status == "accepted" and accepted.superseded_by
    stale = await review.create(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id="chapter-1",
        base_revision_id=document.id,
        draft=draft,
        source=FindingSource.HUMAN,
        author="Owner",
        idempotency_key="finding-stale",
    )
    with pytest.raises(ReviewConflict, match="base_revision_changed"):
        await review.accept(tenant_id=tenant.id, project_id=project.id, finding_id=stale.id)
    await review.rollback(tenant_id=tenant.id, project_id=project.id, finding_id=finding.id)
    async with database.session() as session:
        current = (
            await session.scalars(
                select(NovelDocumentRevisionModel).where(
                    NovelDocumentRevisionModel.project_id == project.id,
                    NovelDocumentRevisionModel.chapter_id == "chapter-1",
                    NovelDocumentRevisionModel.status == "adopted",
                )
            )
        ).one()
        assert current.revision_number == 3
        assert current.blocks == [item.model_dump(mode="json") for item in blocks()]
