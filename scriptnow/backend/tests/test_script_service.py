import pytest
from sqlalchemy import select

from scriptnow.platform.context_retrieval import ContextRequest, RetrievalMode, RetrievalPolicy
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectEventModel,
    ProjectMedium,
    ProjectModel,
    TenantModel,
)
from scriptnow.script.context import ScriptSceneContextAdapter
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import (
    BlueprintAnchorDraft,
    BlueprintDraft,
    CandidateStatus,
    RevisionStatus,
    ScriptBlueprintCandidateModel,
    ScriptStoryCoreCandidateModel,
    StoryCoreDetails,
    StoryCoreDraft,
)
from scriptnow.script.project import initialize_script_project
from scriptnow.script.service import ScriptConflict, ScriptDomainError, ScriptService
from scriptnow.script.story_map import Episode, Scene, ScriptStoryBeat


def core_drafts(prefix: str = "Direction") -> tuple[StoryCoreDraft, ...]:
    return tuple(
        StoryCoreDraft(
            title=f"{prefix} {index}",
            concept=f"A sufficiently detailed concept for direction number {index}.",
            angles=("identity", "desire", "obstacle", "stakes", "change"),
            details=StoryCoreDetails(
                narrative_engine=("deadline",),
                viewpoint_anchor=("witness",),
                pacing_recipe=("slow burn",),
                market_judgement=("contained mystery",),
            ),
        )
        for index in range(1, 4)
    )


@pytest.fixture
async def script_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Harbor",
            medium=ProjectMedium.SCRIPT,
            direction={"script_format": "chinese", "structure": "three_act"},
        )
        session.add(project)
        await session.flush()
        await initialize_script_project(session, project)
    yield ScriptService(database), database, tenant, other, project
    await database.dispose()


@pytest.mark.asyncio
async def test_story_core_always_has_three_candidates_revision_expires_old_and_one_adopted(
    script_data,
) -> None:
    service, database, tenant, _, project = script_data
    with pytest.raises(ScriptDomainError, match="exactly three"):
        await service.generate_story_cores(
            tenant_id=tenant.id, project_id=project.id, drafts=core_drafts()[:2]
        )
    await service.generate_story_cores(
        tenant_id=tenant.id, project_id=project.id, drafts=core_drafts("First")
    )
    second = await service.generate_story_cores(
        tenant_id=tenant.id,
        project_id=project.id,
        drafts=core_drafts("Revised"),
        revision_feedback="Make it more intimate.",
    )
    adopted = await service.adopt_story_core(
        tenant_id=tenant.id, project_id=project.id, candidate_id=second[1].id
    )
    assert adopted.id == second[1].id
    with pytest.raises(ScriptConflict, match="unavailable|already"):
        await service.adopt_story_core(
            tenant_id=tenant.id, project_id=project.id, candidate_id=second[0].id
        )
    with pytest.raises(ScriptConflict, match="locks the divergence"):
        await service.generate_story_cores(
            tenant_id=tenant.id,
            project_id=project.id,
            drafts=core_drafts("Too late"),
        )
    async with database.session() as session:
        records = (
            await session.scalars(
                select(ScriptStoryCoreCandidateModel).order_by(
                    ScriptStoryCoreCandidateModel.generation,
                    ScriptStoryCoreCandidateModel.ordinal,
                )
            )
        ).all()
        assert len(records) == 6
        assert all(item.status == CandidateStatus.EXPIRED for item in records[:3])
        assert [item.status for item in records[3:]] == ["expired", "adopted", "expired"]
        assert records[0].revision_feedback == "Make it more intimate."


async def adopt_core_blueprint(service, tenant, project) -> None:
    candidates = await service.generate_story_cores(
        tenant_id=tenant.id, project_id=project.id, drafts=core_drafts()
    )
    await service.adopt_story_core(
        tenant_id=tenant.id, project_id=project.id, candidate_id=candidates[0].id
    )
    await service.adopt_blueprint(
        tenant_id=tenant.id,
        project_id=project.id,
        draft=BlueprintDraft(
            anchors=(
                BlueprintAnchorDraft(
                    id="character:lin", kind="character", name="Lin", payload={"arc": "trust"}
                ),
                BlueprintAnchorDraft(id="event:blackout", kind="event", name="Third blackout"),
                BlueprintAnchorDraft(
                    id="foreshadow:stamp", kind="foreshadow", name="Today's postmark"
                ),
            )
        ),
    )


def episodes(title: str = "The Letter") -> tuple[Episode, ...]:
    return (
        Episode(
            id="episode-1",
            ordinal=1,
            title="Night One",
            scenes=(
                Scene(
                    id="scene-1",
                    ordinal=1,
                    title=title,
                    duration_seconds_target=120,
                    beats=(
                        ScriptStoryBeat(
                            id="beat-1",
                            objective="Lin finds the letter.",
                            anchor_ids=("character:lin", "foreshadow:stamp"),
                        ),
                    ),
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_blueprint_anchor_and_story_map_candidate_impact_version_conflict(
    script_data,
) -> None:
    service, _, tenant, _, project = script_data
    with pytest.raises(ScriptConflict, match="StoryCore"):
        await service.adopt_blueprint(
            tenant_id=tenant.id,
            project_id=project.id,
            draft=BlueprintDraft(anchors=(BlueprintAnchorDraft(id="x", kind="event", name="X"),)),
        )
    await adopt_core_blueprint(service, tenant, project)
    candidate = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        episodes=episodes(),
        idempotency_key="structure-1",
    )
    replay = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        episodes=episodes("ignored replay"),
        idempotency_key="structure-1",
    )
    assert replay.id == candidate.id
    assert candidate.impact == {"added_units": 3, "removed_units": 0, "retained_units": 0}
    story_map = await service.adopt_structure(
        tenant_id=tenant.id, project_id=project.id, candidate_id=candidate.id
    )
    assert story_map.version == 2
    with pytest.raises(ScriptConflict, match="version conflict"):
        await service.propose_structure(
            tenant_id=tenant.id,
            project_id=project.id,
            expected_version=1,
            episodes=episodes(),
            idempotency_key="stale",
        )
    bad = episodes()[0].model_copy(
        update={
            "scenes": (
                episodes()[0]
                .scenes[0]
                .model_copy(
                    update={
                        "beats": (
                            ScriptStoryBeat(id="bad", objective="Bad", anchor_ids=("unknown",)),
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ScriptDomainError, match="unknown blueprint"):
        await service.propose_structure(
            tenant_id=tenant.id,
            project_id=project.id,
            expected_version=2,
            episodes=(bad,),
            idempotency_key="bad-anchor",
        )


@pytest.mark.asyncio
async def test_blueprint_revision_replaces_active_candidate_and_records_feedback(
    script_data,
) -> None:
    service, database, tenant, _, project = script_data
    cores = await service.generate_story_cores(
        tenant_id=tenant.id, project_id=project.id, drafts=core_drafts()
    )
    await service.adopt_story_core(
        tenant_id=tenant.id, project_id=project.id, candidate_id=cores[0].id
    )
    first = await service.propose_blueprint(
        tenant_id=tenant.id,
        project_id=project.id,
        draft=BlueprintDraft(
            anchors=(
                BlueprintAnchorDraft(
                    id="character:lin",
                    kind="character",
                    name="Lin",
                    payload={"arc": "trust"},
                ),
            )
        ),
        idempotency_key="blueprint-first",
    )
    revised = await service.propose_blueprint(
        tenant_id=tenant.id,
        project_id=project.id,
        draft=BlueprintDraft(
            anchors=(
                BlueprintAnchorDraft(
                    id="character:lin",
                    kind="character",
                    name="Lin",
                    payload={"arc": "acceptance"},
                ),
                BlueprintAnchorDraft(
                    id="arc:main",
                    kind="arc",
                    name="The cost of remembering",
                ),
            )
        ),
        idempotency_key="blueprint-revised",
        revision_feedback="Add a complete dramatic arc.",
    )

    async with database.session() as session:
        persisted_first = await session.get(ScriptBlueprintCandidateModel, first.id)
        persisted_revised = await session.get(ScriptBlueprintCandidateModel, revised.id)
        assert persisted_first is not None
        assert persisted_first.status == CandidateStatus.EXPIRED
        assert persisted_revised is not None
        assert persisted_revised.status == CandidateStatus.ACTIVE
        event = (
            await session.scalars(
                select(ProjectEventModel).where(
                    ProjectEventModel.event_key
                    == f"script:blueprint:propose:{revised.id}"
                )
            )
        ).one()
        assert event.payload["action"] == "blueprint.revise"
        assert event.payload["feedback"] == "Add a complete dramatic arc."


def document_blocks(action: str = "Lin opens the letter.") -> tuple[ScriptBlock, ...]:
    return (
        ScriptBlock(para_id="p1", type="slugline", text="内景 灯塔 夜"),
        ScriptBlock(para_id="p2", type="action", text=action),
        ScriptBlock(para_id="p3", type="character", text="林"),
        ScriptBlock(para_id="p4", type="dialogue", text="这不可能。"),
    )


@pytest.mark.asyncio
async def test_writer_candidate_adoption_stale_base_format_and_context_pack(script_data) -> None:
    service, _, tenant, other, project = script_data
    await adopt_core_blueprint(service, tenant, project)
    structure = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        episodes=episodes(),
        idempotency_key="structure",
    )
    await service.adopt_structure(
        tenant_id=tenant.id, project_id=project.id, candidate_id=structure.id
    )
    with pytest.raises(ScriptDomainError, match="slugline"):
        await service.propose_document(
            tenant_id=tenant.id,
            project_id=project.id,
            scene_id="scene-1",
            blocks=(ScriptBlock(para_id="x", type="action", text="No slugline"),),
            idempotency_key="invalid",
        )
    first = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        scene_id="scene-1",
        blocks=document_blocks(),
        idempotency_key="draft-1",
    )
    await service.adopt_document(tenant_id=tenant.id, project_id=project.id, revision_id=first.id)
    second = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        scene_id="scene-1",
        blocks=document_blocks("Lin burns the letter."),
        idempotency_key="draft-2",
    )
    competing = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        scene_id="scene-1",
        blocks=document_blocks("Lin hides the letter."),
        idempotency_key="draft-3",
    )
    await service.adopt_document(tenant_id=tenant.id, project_id=project.id, revision_id=second.id)
    with pytest.raises(ScriptConflict, match="stale"):
        await service.adopt_document(
            tenant_id=tenant.id, project_id=project.id, revision_id=competing.id
        )
    async with service.database.session() as session:
        stale = await session.get(type(competing), competing.id)
        assert stale is not None and stale.status == RevisionStatus.SUPERSEDED
    pack = await service.context_pack(
        tenant_id=tenant.id, project_id=project.id, scene_id="scene-1"
    )
    assert {item["id"] for item in pack["anchors"]} == {
        "character:lin",
        "foreshadow:stamp",
    }
    assert pack["scene"]["id"] == "scene-1"
    assert pack["scene_ordinal"] == 1
    assert pack["story_map_version"] == 2
    assert all(item["id"] != "event:blackout" for item in pack["anchors"])
    assert pack["adopted_scenes"][0]["revision_id"] == second.id
    async with service.database.session() as session:
        decisions = (
            await session.scalars(
                select(ProjectEventModel)
                .where(ProjectEventModel.stream_key == f"project:{project.id}")
                .order_by(ProjectEventModel.sequence)
            )
        ).all()
        assert [item.payload["action"] for item in decisions] == [
            "script_story_core.propose",
            "story_core.adopt",
            "blueprint.propose",
            "blueprint.adopt",
            "story_map.adopt",
            "script_document.adopt",
            "script_document.adopt",
        ]
        assert [item.sequence for item in decisions] == [1, 2, 3, 4, 5, 6, 7]
        proposed = decisions[0]
        assert proposed.event_type == "conversation"
        assert proposed.actor == {"type": "agent", "role": "director"}
        assert len(proposed.payload["candidates"]) == 3
        adopted = decisions[1]
        assert adopted.actor == {"type": "user"}
        assert adopted.payload["candidate"]["title"] == "Direction 1"
    with pytest.raises(ScriptDomainError, match="tenant scope"):
        await service.context_pack(tenant_id=other.id, project_id=project.id, scene_id="scene-1")


@pytest.mark.asyncio
async def test_propose_document_merges_same_speaker_dialogue_fragments(
    script_data,
) -> None:
    service, _, tenant, _, project = script_data
    await adopt_core_blueprint(service, tenant, project)
    structure = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        episodes=episodes(),
        idempotency_key="structure-merge",
    )
    await service.adopt_structure(
        tenant_id=tenant.id, project_id=project.id, candidate_id=structure.id
    )
    revision = await service.propose_document(
        tenant_id=tenant.id,
        project_id=project.id,
        scene_id="scene-1",
        blocks=(
            ScriptBlock(para_id="p1", type="slugline", text="内景 灯塔 夜"),
            ScriptBlock(para_id="p2", type="action", text="Lin faces the buyer."),
            ScriptBlock(para_id="c1", type="character", text="宋晚"),
            ScriptBlock(para_id="d1", type="dialogue", text="下调后的价格"),
            ScriptBlock(para_id="c2", type="character", text="宋晚"),
            ScriptBlock(para_id="d2", type="dialogue", text="刚好落在出价区间。"),
        ),
        idempotency_key="merged-draft",
    )

    async with service.database.session() as session:
        stored = await session.get(type(revision), revision.id)
        assert stored is not None
        blocks = stored.blocks
    dialogues = [item for item in blocks if item["type"] == "dialogue"]
    characters = [item for item in blocks if item["type"] == "character"]
    assert len(dialogues) == 1
    assert len(characters) == 1
    assert dialogues[0]["text"] == "下调后的价格，刚好落在出价区间。"


@pytest.mark.asyncio
async def test_script_context_adapter_keeps_scene_contract_and_blueprint_traceable(
    script_data,
) -> None:
    service, database, tenant, _, project = script_data
    await adopt_core_blueprint(service, tenant, project)
    structure = await service.propose_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        expected_version=1,
        episodes=episodes(),
        idempotency_key="context-structure",
    )
    await service.adopt_structure(
        tenant_id=tenant.id,
        project_id=project.id,
        candidate_id=structure.id,
    )
    request = ContextRequest(
        tenant_id=tenant.id,
        project_id=project.id,
        domain="script",
        stage="scene_candidate",
        operation="script.scene.generate",
        unit_ref="scene-1",
        required_dimensions=("scene_contract", "continuity", "blueprint"),
        risk_level="normal",
        policy_ref="script-context-v1",
    )
    policy = RetrievalPolicy(
        allowed_sources=("script_story_map", "script_blueprint", "script_revision"),
        retrieval_modes=(RetrievalMode.CANONICAL,),
        coverage_requirements={
            "scene_contract": 1.0,
            "continuity": 1.0,
            "blueprint": 1.0,
        },
        token_limit=8000,
        timeout_seconds=10,
        max_iterations=1,
        conflict_policy="surface",
        external_research_enabled=False,
    )

    seed = await ScriptSceneContextAdapter(
        database,
        token_counter=lambda value: len(value.split()),
    ).canonical_context(request, policy)

    assert seed.coverage == {
        "scene_contract": 1.0,
        "blueprint": 1.0,
        "continuity": 1.0,
    }
    assert seed.domain_state["scene_ordinal"] == 1
    assert seed.canonical_facts[0]["kind"] == "scene_contract"
    assert seed.canonical_facts[0]["scene"]["id"] == "scene-1"
    assert {item.source_type for item in seed.evidence} == {
        "script_story_map",
        "script_blueprint",
    }


def test_story_core_schema_requires_five_angles_and_blueprint_anchor_ids() -> None:
    with pytest.raises(ValueError):
        StoryCoreDraft(
            title="Too small",
            concept="A sufficiently long concept.",
            angles=("one",),
            details=StoryCoreDetails(
                narrative_engine=(), viewpoint_anchor=(), pacing_recipe=(), market_judgement=()
            ),
        )
