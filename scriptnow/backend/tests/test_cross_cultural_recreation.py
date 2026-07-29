from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from scriptnow.novel.cross_cultural_recreation.api import (
    _governance_manifest_requirements,
)
from scriptnow.novel.cross_cultural_recreation.domain import (
    ChapterPipelineStatus,
    ChapterRevisionKind,
    RecreationArtifactKind,
    RecreationArtifactStatus,
    RecreationStatus,
)
from scriptnow.novel.cross_cultural_recreation.generator import (
    CrossCulturalRecreationGenerator,
    RecreationGenerationError,
    SourceStoryModelPayload,
)
from scriptnow.novel.cross_cultural_recreation.service import (
    CrossCulturalRecreationError,
    CrossCulturalRecreationService,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectEventModel,
    ProjectMedium,
    ProjectModel,
    ProjectSource,
    ProjectWorkflow,
    TenantModel,
)


@pytest.fixture
async def recreation_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Recreation Studio")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="跨文化再创作实验",
            medium=ProjectMedium.NOVEL,
            source_mode=ProjectSource.ADAPTATION,
            workflow_kind=ProjectWorkflow.CROSS_CULTURAL_RECREATION,
            direction={},
        )
        session.add(project)
        await session.flush()
    yield database, tenant, project
    await database.dispose()


@pytest.mark.asyncio
async def test_recreation_versions_candidates_and_requires_explicit_adoption(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult mobile fiction readers",
        distribution_context="serialized mobile fiction",
    )

    first = await service.record_artifacts(
        recreation_id=recreation.id,
        kind=RecreationArtifactKind.RECREATION_STRATEGY,
        payloads=({"title": "A"}, {"title": "B"}, {"title": "C"}),
        idempotency_key="strategy-1",
    )
    repeated = await service.record_artifacts(
        recreation_id=recreation.id,
        kind=RecreationArtifactKind.RECREATION_STRATEGY,
        payloads=({"title": "ignored"},),
        idempotency_key="strategy-1",
    )

    assert [item.id for item in repeated] == [item.id for item in first]
    assert all(str(item.status) == RecreationArtifactStatus.CANDIDATE for item in first)
    adopted = await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=first[1].id,
    )
    assert str(adopted.status) == RecreationArtifactStatus.ADOPTED
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.STRATEGY_ADOPTED

    async with database.session() as session:
        events = list(
            await session.scalars(
                select(ProjectEventModel)
                .where(ProjectEventModel.project_id == project.id)
                .order_by(ProjectEventModel.sequence)
            )
        )
    assert [item.payload["action"] for item in events] == [
        "cross_cultural.recreation_strategy.propose",
        "cross_cultural.recreation_strategy.propose",
        "cross_cultural.recreation_strategy.propose",
        "cross_cultural.recreation_strategy.adopt",
    ]
    assert events[-1].payload["title"] == "已确认归化策略"


@pytest.mark.asyncio
async def test_pilot_and_scale_plan_each_require_explicit_adoption(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult mobile fiction readers",
        distribution_context="serialized mobile fiction",
    )

    pilot = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.PILOT,
            payloads=({"unit_title": "pilot"},),
            idempotency_key="pilot-1",
        )
    )[0]
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.PILOT_READY

    await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=pilot.id,
    )
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.PILOT_ADOPTED

    plan = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.SCALE_PLAN,
            payloads=({"work_packages": [{"order": 1}]},),
            idempotency_key="scale-1",
        )
    )[0]
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.SCALE_PLAN_READY

    await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=plan.id,
    )
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.SCALE_PLAN_ADOPTED


@pytest.mark.asyncio
async def test_production_units_follow_the_adopted_plan_without_fixed_package_count(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult mobile fiction readers",
        distribution_context="serialized mobile fiction",
    )
    plan = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.SCALE_PLAN,
            payloads=(
                {
                    "work_packages": [
                        {"order": "opening"},
                        {"order": "reversal"},
                    ]
                },
            ),
            idempotency_key="scale-production",
        )
    )[0]
    await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=plan.id,
    )

    opening_v1 = await service.record_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="opening",
        payload={"title": "Opening v1"},
        idempotency_key="opening-1",
    )
    opening_v2 = await service.record_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="opening",
        payload={"title": "Opening v2"},
        idempotency_key="opening-2",
    )
    assert opening_v1.version == 1
    assert opening_v2.version == 2

    await service.adopt_production_unit(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id=opening_v2.id,
    )
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.PRODUCTION_IN_PROGRESS

    reversal = await service.record_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="reversal",
        payload={"title": "Reversal"},
        idempotency_key="reversal-1",
    )
    await service.adopt_production_unit(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id=reversal.id,
    )
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.PRODUCTION_COMPLETE

    await service.sync_project_events(
        tenant_id=tenant.id,
        project_id=project.id,
    )
    async with database.session() as session:
        events = list(
            await session.scalars(
                select(ProjectEventModel).where(
                    ProjectEventModel.project_id == project.id,
                    ProjectEventModel.event_key.like("cross-cultural:production:%"),
                )
            )
        )
    assert len(events) == 5
    assert sum(item.payload["action"].endswith(".adopt") for item in events) == 2


@pytest.mark.asyncio
async def test_chapter_pipeline_persists_run_review_manual_revision_and_adoption(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult mobile fiction readers",
        distribution_context="serialized mobile fiction",
    )
    plan = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.SCALE_PLAN,
            payloads=({"work_packages": [{"order": "chapter-1"}]},),
            idempotency_key="chapter-plan",
        )
    )[0]
    await service.adopt(tenant_id=tenant.id, project_id=project.id, artifact_id=plan.id)

    running = await service.start_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="chapter-1",
        idempotency_key="chapter-run",
        context_snapshot={
            "scale_plan_artifact_id": plan.id,
            "earlier_adopted_units": [],
        },
    )
    assert str(running.pipeline_status) == ChapterPipelineStatus.DRAFTING
    assert running.payload == {}

    candidate = await service.complete_production_unit(
        unit_id=running.id,
        payload={
            "title": "The Call",
            "target_language_draft": "A complete chapter draft.",
            "recreation_rationale": [{"source_function": "loss"}],
            "gene_trace": [{"gene": "last call"}],
            "quality_self_check": [{"gate": "continuity", "result": "pass"}],
        },
    )
    assert str(candidate.pipeline_status) == ChapterPipelineStatus.REVIEW_PENDING

    with pytest.raises(CrossCulturalRecreationError, match="先完成章节审读"):
        await service.adopt_production_unit(
            tenant_id=tenant.id,
            project_id=project.id,
            unit_id=candidate.id,
        )

    reviewed = await service.review_production_unit(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id=candidate.id,
    )
    assert str(reviewed.pipeline_status) == ChapterPipelineStatus.READY_FOR_DECISION
    assert reviewed.review_report["verdict"] == "pass"

    manual = await service.revise_production_unit(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id=reviewed.id,
        title="The Last Call",
        draft="The author revised the complete chapter.",
        idempotency_key="manual-v2",
    )
    assert manual.version == 2
    assert str(manual.revision_kind) == ChapterRevisionKind.MANUAL
    assert manual.source_unit_id == reviewed.id
    assert str(manual.pipeline_status) == ChapterPipelineStatus.REVIEW_PENDING
    assert manual.context_snapshot["scale_plan_artifact_id"] == plan.id

    await service.review_production_unit(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id=manual.id,
    )
    adopted = await service.adopt_production_unit(
        tenant_id=tenant.id,
        project_id=project.id,
        unit_id=manual.id,
    )
    assert str(adopted.status) == RecreationArtifactStatus.ADOPTED
    assert str(adopted.pipeline_status) == ChapterPipelineStatus.ADOPTED


@pytest.mark.asyncio
async def test_chapter_failure_is_isolated_and_retriable(recreation_data) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult mobile fiction readers",
        distribution_context="serialized mobile fiction",
    )
    plan = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.SCALE_PLAN,
            payloads=({"work_packages": [{"order": "chapter-1"}, {"order": "chapter-2"}]},),
            idempotency_key="failure-plan",
        )
    )[0]
    await service.adopt(tenant_id=tenant.id, project_id=project.id, artifact_id=plan.id)
    failed = await service.start_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="chapter-1",
        idempotency_key="failed-run",
        context_snapshot={},
    )
    await service.fail_production_unit(unit_id=failed.id, reason="provider timeout")
    retry = await service.start_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="chapter-1",
        idempotency_key="retry-run",
        context_snapshot={},
    )
    other = await service.start_production_unit(
        recreation_id=recreation.id,
        scale_plan_artifact_id=plan.id,
        work_package_key="chapter-2",
        idempotency_key="other-run",
        context_snapshot={},
    )
    assert retry.version == 2
    assert other.version == 1


@pytest.mark.asyncio
async def test_recreation_rejects_an_ordinary_novel_project(recreation_data) -> None:
    database, tenant, _ = recreation_data
    async with database.session() as session:
        project = ProjectModel(
            tenant_id=tenant.id,
            name="ordinary",
            medium=ProjectMedium.NOVEL,
            source_mode=ProjectSource.ORIGINAL,
            workflow_kind=ProjectWorkflow.ORIGINAL,
            direction={},
        )
        session.add(project)
        await session.flush()

    with pytest.raises(CrossCulturalRecreationError, match="只能绑定"):
        await CrossCulturalRecreationService(database).create(
            tenant_id=tenant.id,
            project_id=project.id,
            source_language="zh-CN",
            target_language="en-US",
            target_market="North America",
            target_audience="adult readers",
            distribution_context="ebook",
        )


def test_structured_output_failure_is_a_product_error_not_raw_validation() -> None:
    with pytest.raises(RecreationGenerationError, match="缺少必要结构"):
        CrossCulturalRecreationGenerator._validated_payload(
            SourceStoryModelPayload,
            '{"story_summary":"too short"}',
        )


def test_production_language_gate_rejects_clear_script_mismatch() -> None:
    with pytest.raises(RecreationGenerationError, match="目标创作语言"):
        CrossCulturalRecreationGenerator._validate_target_language(
            draft="这是一段完全使用中文返回的候选正文。",
            target_language="en-US",
        )

    CrossCulturalRecreationGenerator._validate_target_language(
        draft="This candidate is written in the configured target language.",
        target_language="en-US",
    )


@pytest.mark.asyncio
async def test_pilot_uses_traceable_context_without_loading_full_source(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    generator = CrossCulturalRecreationGenerator(database, AsyncMock())
    generator._source_text = AsyncMock(return_value="must not be loaded")  # type: ignore[method-assign]
    generator._generate = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "unit_title": "Pilot",
            "rationale": "A bounded representative unit for the target audience.",
            "target_language_draft": "Draft text. " * 40,
            "change_notes": [{"source_function": "test"}, {"source_function": "test-2"}],
            "gene_trace": [{"gene": "one"}, {"gene": "two"}],
            "open_questions": [],
        }
    )

    await generator.generate_pilot(
        tenant_id=tenant.id,
        project=project,
        idempotency_key="pilot-context",
        source_model={},
        target_contract={},
        strategy={},
        feedback=None,
        context_pack={"evidence": [{"ref_id": "source:pilot"}]},
        retrieval_manifest_id="manifest-pilot",
    )

    generator._source_text.assert_not_awaited()
    call = generator._generate.await_args.kwargs
    assert "source:pilot" in call["prompt"]
    assert call["context_snapshot"] == {
        "retrieval_manifest_id": "manifest-pilot",
        "task": "cross-cultural-pilot",
    }


@pytest.mark.asyncio
async def test_source_strategy_and_scale_plan_require_traceable_manifests(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    generator = CrossCulturalRecreationGenerator(database, AsyncMock())

    with pytest.raises(RecreationGenerationError, match="源作品分析缺少"):
        await generator.analyze_source(
            tenant_id=tenant.id,
            project=project,
            idempotency_key="source-no-manifest",
            target_contract={},
        )
    with pytest.raises(RecreationGenerationError, match="归化策略缺少"):
        await generator.generate_strategies(
            tenant_id=tenant.id,
            project=project,
            idempotency_key="strategy-no-manifest",
            source_model={},
            target_contract={},
            feedback=None,
        )
    with pytest.raises(RecreationGenerationError, match="整书方案缺少"):
        await generator.generate_scale_plan(
            tenant_id=tenant.id,
            project=project,
            idempotency_key="scale-no-manifest",
            source_model={},
            target_contract={},
            strategy={},
            pilot={},
            feedback=None,
        )


@pytest.mark.asyncio
async def test_governance_artifacts_are_versioned_without_regressing_stage(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult readers",
        distribution_context="mobile fiction",
    )
    strategy = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.RECREATION_STRATEGY,
            payloads=({"title": "adopted"},),
            idempotency_key="governance-stage",
        )
    )[0]
    await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=strategy.id,
    )
    mapping = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.CULTURAL_MAPPING_SET,
            payloads=({"mappings": [{"mapping_key": "family-duty"}]},),
            idempotency_key="mapping-v1",
            adopt=True,
        )
    )[0]

    assert str(mapping.status) == RecreationArtifactStatus.ADOPTED
    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.STRATEGY_ADOPTED


@pytest.mark.asyncio
async def test_adopting_governance_candidate_does_not_regress_stage(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    service = CrossCulturalRecreationService(database)
    recreation = await service.create(
        tenant_id=tenant.id,
        project_id=project.id,
        source_language="zh-CN",
        target_language="en-US",
        target_market="North America",
        target_audience="adult readers",
        distribution_context="mobile fiction",
    )
    strategy = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.RECREATION_STRATEGY,
            payloads=({"title": "adopted"},),
            idempotency_key="governance-adopt-stage",
        )
    )[0]
    await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=strategy.id,
    )
    decision = (
        await service.record_artifacts(
            recreation_id=recreation.id,
            kind=RecreationArtifactKind.PROTECTION_CONFLICT_DECISION,
            payloads=(
                {
                    "decisions": [
                        {
                            "protected_element": "ending",
                            "decision": "preserve",
                        }
                    ]
                },
            ),
            idempotency_key="decision-candidate",
        )
    )[0]

    await service.adopt(
        tenant_id=tenant.id,
        project_id=project.id,
        artifact_id=decision.id,
    )

    current = await service.get(tenant_id=tenant.id, project_id=project.id)
    assert str(current.status) == RecreationStatus.STRATEGY_ADOPTED


def test_governance_artifacts_become_explicit_manifest_requirements() -> None:
    dimensions, coverage = _governance_manifest_requirements(
        {
            RecreationArtifactKind.CULTURAL_MAPPING_SET.value: {"mappings": []},
            RecreationArtifactKind.PROTECTION_CONFLICT_DECISION.value: {
                "decisions": []
            },
        }
    )

    assert dimensions == ("cultural_mapping", "protection_decisions")
    assert coverage == {
        "cultural_mapping": 1.0,
        "protection_decisions": 1.0,
    }


@pytest.mark.asyncio
async def test_production_identity_mismatch_is_rewritten_not_relabeled(
    recreation_data,
) -> None:
    database, tenant, project = recreation_data
    generator = CrossCulturalRecreationGenerator(database, AsyncMock())
    generator._source_text = AsyncMock(return_value="source evidence")  # type: ignore[method-assign]
    payload = {
        "work_package_key": "later-act",
        "title": "Wrong act",
        "target_language_draft": "Draft text. " * 40,
        "recreation_rationale": [{"source_function": "test"}],
        "gene_trace": [{"gene": "test"}],
        "continuity_updates": [],
        "quality_self_check": [{"gate": "test", "result": True}],
        "open_questions": [],
    }
    corrected = {**payload, "work_package_key": "act-2", "title": "Correct act"}
    generator._generate = AsyncMock(  # type: ignore[method-assign]
        side_effect=[payload, corrected]
    )

    result = await generator.generate_production_unit(
        tenant_id=tenant.id,
        project=project,
        idempotency_key="identity-test",
        source_model={},
        target_contract={"target_language": "en-US"},
        strategy={},
        pilot={},
        scale_plan={"work_packages": [{"order": "act-2"}]},
        work_package={"order": "act-2", "title": "Act two"},
        adopted_units=[],
        feedback=None,
        context_pack={"evidence": [{"ref_id": "source:12"}]},
        retrieval_manifest_id="manifest-12",
    )

    assert result["work_package_key"] == "act-2"
    assert generator._generate.await_count == 2
    correction_call = generator._generate.await_args_list[1].kwargs
    assert correction_call["stage"] == "cross_cultural_production_identity_repair"
    assert "Rewrite it as the requested package" in correction_call["prompt"]
    assert "source:12" in correction_call["prompt"]
    assert correction_call["context_snapshot"] == {
        "retrieval_manifest_id": "manifest-12",
        "work_package_key": "act-2",
    }
    generator._source_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_requires_traceable_retrieval_context(recreation_data) -> None:
    database, tenant, project = recreation_data
    generator = CrossCulturalRecreationGenerator(database, AsyncMock())

    with pytest.raises(RecreationGenerationError, match="可追溯检索上下文"):
        await generator.generate_production_unit(
            tenant_id=tenant.id,
            project=project,
            idempotency_key="missing-context",
            source_model={},
            target_contract={"target_language": "en-US"},
            strategy={},
            pilot={},
            scale_plan={"work_packages": [{"order": "act-2"}]},
            work_package={"order": "act-2", "title": "Act two"},
            adopted_units=[],
            feedback=None,
        )
