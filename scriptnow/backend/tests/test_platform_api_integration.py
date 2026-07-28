import asyncio
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from scriptnow.app import create_app
from scriptnow.novel.cross_cultural_recreation.generator import (
    CrossCulturalRecreationGenerator,
)
from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.novel.project import (
    NovelPlanModel,
    NovelStoryMapModel,
    initialize_novel_project,
)
from scriptnow.platform.agent_runtime import (
    AgentRuntime,
    AgentRuntimeResult,
    AgentRuntimeTimeoutError,
)
from scriptnow.platform.auth import AuthService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentStateModel,
    AgentTemplateVersionModel,
    AuditLogModel,
    CreativeArtifactRefModel,
    CreativeCheckpointModel,
    CreativeOperationModel,
    CreativeStageRunModel,
    CreditLedgerModel,
    LanguageModelModel,
    MemoryAuditModel,
    MemoryEntryModel,
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    ProjectSource,
    ProjectWorkflow,
    ProviderModel,
    ProviderStatus,
    RagChunkModel,
    RuntimeConfigSnapshotModel,
    TenantAgentConfigModel,
    TenantModel,
    TierModel,
    TokenAccountModel,
    TokenUsageModel,
    UsageReservationModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)
from scriptnow.platform.translation_contracts import TranslationUnit
from scriptnow.script.project import ScriptPlanModel, ScriptStoryMapModel


@pytest.fixture
async def platform_api(tmp_path):
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    settings = Settings(
        access_token_secret="test-secret-that-is-at-least-24-bytes",
        workspace_root=str(tmp_path / "workspaces"),
    )
    auth = AuthService(database, settings)
    tenant_a, _ = await auth.create_tenant_owner(
        tenant_name="Studio A", email="a@example.com", password="correct horse battery staple"
    )
    tenant_b, _ = await auth.create_tenant_owner(
        tenant_name="Studio B", email="b@example.com", password="correct horse battery staple"
    )
    async with database.session() as session:
        tier = TierModel(code="plus", name="Plus", rank=10, monthly_token_quota=10_000)
        provider = ProviderModel(key="mock", name="Mock", status=ProviderStatus.CONNECTED)
        session.add_all([tier, provider])
        await session.flush()
        model = LanguageModelModel(
            key="mock-v1",
            display_name="Mock V1",
            provider_id=provider.id,
            agentscope_class="OpenAIChatModel",
            min_tier_id=tier.id,
            input_price_per_million=1,
            output_price_per_million=2,
        )
        session.add(model)
        await session.flush()
        session.add(
            AgentTemplateVersionModel(
                role_key="writer",
                version=1,
                soul="Write deterministically.",
                default_model_id=model.id,
                published=True,
            )
        )
        session.add_all(
            [
                TokenAccountModel(
                    tenant_id=tenant.id,
                    tier="plus",
                    period_key="2026-07",
                    monthly_available=10_000,
                    credits_available=0,
                )
                for tenant in (tenant_a, tenant_b)
            ]
        )
    app = create_app(database=database, settings=settings)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client_a,
        AsyncClient(transport=transport, base_url="http://test") as client_b,
    ):
        yield client_a, client_b, database
    await app.state.active_runs.cancel_all()
    await database.dispose()


async def login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return client.cookies["sf_csrf"]


@pytest.mark.asyncio
async def test_translation_background_run_persists_lineage(
    platform_api, monkeypatch
) -> None:
    client, _, database = platform_api
    await login(client, "a@example.com")
    async with database.session() as session:
        tenant = (
            await session.scalars(
                select(TenantModel).where(TenantModel.name == "Studio A")
            )
        ).one()
        source = ProjectModel(
            tenant_id=tenant.id,
            name="Source Novel",
            medium=ProjectMedium.NOVEL,
            direction={"language": "zh-CN"},
        )
        translation = ProjectModel(
            tenant_id=tenant.id,
            name="Source Novel · en-US",
            medium=ProjectMedium.TRANSLATION,
            direction={
                "source_project_id": "",
                "source_language": "zh-CN",
                "target_language": "en-US",
                "translation_mode": "faithful",
            },
        )
        session.add_all([source, translation])
        await session.flush()
        translation.direction = {
            **translation.direction,
            "source_project_id": source.id,
        }
        await initialize_novel_project(session, source)
        story_map = (
            await session.scalars(
                select(NovelStoryMapModel).where(
                    NovelStoryMapModel.project_id == source.id
                )
            )
        ).one()
        story_map.volumes = [
            {
                "id": "volume-1",
                "title": "第一卷",
                "chapters": [{"id": "chapter-1", "title": "来信", "beats": []}],
            }
        ]
        session.add(
            NovelDocumentRevisionModel(
                project_id=source.id,
                chapter_id="chapter-1",
                revision_number=1,
                blocks=[
                    {"block_id": "p1", "type": "prose", "text": "雨落在窗沿。"}
                ],
                status=NovelRevisionStatus.ADOPTED,
                idempotency_key="translation-source",
            )
        )
        translation_id = translation.id

    async def fake_translate(self, *, units, **kwargs):
        unit = units[0]
        return (
            TranslationUnit(
                titles={key: "The Letter" for key in unit.titles},
                blocks=tuple(
                    {**block, "text": "Rain traced the window."}
                    for block in unit.blocks
                ),
            ),
        )

    monkeypatch.setattr(
        "scriptnow.platform.translation.FaithfulTranslationService.translate",
        fake_translate,
    )
    queued = await client.post(
        f"/translation/projects/{translation_id}/chapters/chapter-1/translate",
        params={"background": "true"},
    )
    assert queued.status_code == 200
    payload = queued.json()
    assert payload["run_id"]
    for _ in range(500):
        status = await client.get(
            f"/translation/projects/{translation_id}/runs/{payload['run_id']}"
        )
        assert status.status_code == 200
        if status.json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.02)
    assert status.json()["status"] == "succeeded"

    operation = None
    artifacts = []
    checkpoints = []
    for _ in range(100):
        async with database.session() as session:
            operation = (
                await session.scalars(
                    select(CreativeOperationModel).where(
                        CreativeOperationModel.id == payload["operation_id"]
                    )
                )
            ).one()
            artifacts = list(
                await session.scalars(
                    select(CreativeArtifactRefModel).where(
                        CreativeArtifactRefModel.operation_id == operation.id
                    )
                )
            )
            checkpoints = list(
                await session.scalars(
                    select(CreativeCheckpointModel).where(
                        CreativeCheckpointModel.operation_id == operation.id
                    )
                )
            )
        if len(artifacts) == 1 and len(checkpoints) == 1:
            break
        await asyncio.sleep(0.02)
    assert operation is not None
    assert operation.status == "succeeded"
    assert [item.artifact_type for item in artifacts] == [
        "translation_revision"
    ]
    assert len(checkpoints) == 1


@pytest.mark.asyncio
async def test_recreation_source_analysis_background_run_persists_lineage(
    platform_api, monkeypatch
) -> None:
    client, _, database = platform_api
    csrf = await login(client, "a@example.com")
    async with database.session() as session:
        tenant = (
            await session.scalars(
                select(TenantModel).where(TenantModel.name == "Studio A")
            )
        ).one()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Cross-cultural Story",
            medium=ProjectMedium.NOVEL,
            source_mode=ProjectSource.ADAPTATION,
            workflow_kind=ProjectWorkflow.CROSS_CULTURAL_RECREATION,
            direction={},
        )
        session.add(project)
        await session.flush()
        project_id = project.id

    created = await client.post(
        "/cross-cultural-recreations",
        headers={"X-CSRF-Token": csrf},
        json={
            "project_id": project_id,
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_market": "North America",
            "target_audience": "adult mobile fiction readers",
            "distribution_context": "serialized mobile fiction",
        },
    )
    assert created.status_code == 201

    async def fake_analyze_source(self, **kwargs):
        del self, kwargs
        return {
            "story_summary": "A woman confronts a buried betrayal.",
            "story_genes": [
                {
                    "name": "betrayal",
                    "narrative_function": "forces the final choice",
                    "evidence": "the last phone call",
                }
            ],
            "cultural_gaps": [
                {
                    "source_element": "family obligation",
                    "implied_social_knowledge": "kinship duty",
                    "reader_failure_risk": "motivation appears weak",
                    "possible_treatment": "rebuild the duty through local institutions",
                }
            ],
            "protected_elements": ["the final call"],
            "uncertainties": [],
        }

    monkeypatch.setattr(
        CrossCulturalRecreationGenerator,
        "analyze_source",
        fake_analyze_source,
    )
    queued = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/analyze-source",
        params={"background": "true"},
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "recreation-source-background",
            "feedback": None,
        },
    )
    assert queued.status_code == 200
    payload = queued.json()
    for _ in range(500):
        status_response = await client.get(
            f"/cross-cultural-recreations/by-project/{project_id}/runs/{payload['run_id']}"
        )
        assert status_response.status_code == 200
        if status_response.json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.02)
    assert status_response.json()["status"] == "succeeded"

    async with database.session() as session:
        operation = (
            await session.scalars(
                select(CreativeOperationModel).where(
                    CreativeOperationModel.id == payload["operation_id"]
                )
            )
        ).one()
        artifacts = list(
            await session.scalars(
                select(CreativeArtifactRefModel).where(
                    CreativeArtifactRefModel.operation_id == operation.id
                )
            )
        )
        checkpoints = list(
            await session.scalars(
                select(CreativeCheckpointModel).where(
                    CreativeCheckpointModel.operation_id == operation.id
                )
            )
        )
        assert operation.status == "succeeded"
        assert [item.artifact_type for item in artifacts] == ["source_story_model"]
        assert len(checkpoints) == 1


@pytest.mark.asyncio
async def test_recreation_strategy_background_run_persists_three_candidates(
    platform_api, monkeypatch
) -> None:
    client, _, database = platform_api
    csrf = await login(client, "a@example.com")
    async with database.session() as session:
        tenant = (
            await session.scalars(
                select(TenantModel).where(TenantModel.name == "Studio A")
            )
        ).one()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Cross-cultural Strategy",
            medium=ProjectMedium.NOVEL,
            source_mode=ProjectSource.ADAPTATION,
            workflow_kind=ProjectWorkflow.CROSS_CULTURAL_RECREATION,
            direction={},
        )
        session.add(project)
        await session.flush()
        project_id = project.id

    created = await client.post(
        "/cross-cultural-recreations",
        headers={"X-CSRF-Token": csrf},
        json={
            "project_id": project_id,
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_market": "North America",
            "target_audience": "adult mobile fiction readers",
            "distribution_context": "serialized mobile fiction",
        },
    )
    assert created.status_code == 201

    async def fake_analyze_source(self, **kwargs):
        del self, kwargs
        return {
            "story_summary": "A woman confronts a buried betrayal.",
            "story_genes": [
                {
                    "name": "betrayal",
                    "narrative_function": "forces the final choice",
                    "evidence": "the last phone call",
                }
            ],
            "cultural_gaps": [
                {
                    "source_element": "family obligation",
                    "implied_social_knowledge": "kinship duty",
                    "reader_failure_risk": "motivation appears weak",
                    "possible_treatment": "rebuild the duty through local institutions",
                }
            ],
            "protected_elements": ["the final call"],
            "uncertainties": [],
        }

    monkeypatch.setattr(
        CrossCulturalRecreationGenerator,
        "analyze_source",
        fake_analyze_source,
    )
    source = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/analyze-source",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "strategy-source", "feedback": None},
    )
    assert source.status_code == 200
    contract = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/target-contract",
        headers={"X-CSRF-Token": csrf},
        json={
            "genre_promise": "emotional suspense",
            "background_policy": "rebuild institutions for the target culture",
            "cultural_distance": "moderate",
            "protected_elements": ["the final call"],
            "allowed_changes": ["names", "locations"],
            "prohibited_changes": ["the final choice"],
            "idempotency_key": "strategy-contract",
        },
    )
    assert contract.status_code == 200

    async def fake_generate_strategies(self, **kwargs):
        del self, kwargs
        return tuple(
            {
                "title": f"Strategy {index}",
                "target_premise": f"Target premise {index} with sufficient detail.",
                "recreation_thesis": f"Recreation thesis {index} with sufficient detail.",
                "localization_decisions": [
                    {
                        "source_function": "betrayal",
                        "target_carrier": "local institution",
                        "causal_reason": "preserve narrative pressure",
                    }
                    for _ in range(3)
                ],
                "retained_genes": ["betrayal", "final choice"],
                "risks": ["flattened motivation"],
                "pilot_unit": f"chapter-{index}",
            }
            for index in range(1, 4)
        )

    monkeypatch.setattr(
        CrossCulturalRecreationGenerator,
        "generate_strategies",
        fake_generate_strategies,
    )
    queued = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/strategies",
        params={"background": "true"},
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "recreation-strategy-background",
            "feedback": "keep the final moral choice",
        },
    )
    assert queued.status_code == 200
    payload = queued.json()
    for _ in range(500):
        status_response = await client.get(
            f"/cross-cultural-recreations/by-project/{project_id}/runs/{payload['run_id']}"
        )
        assert status_response.status_code == 200
        if status_response.json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.02)
    assert status_response.json()["status"] == "succeeded"

    async with database.session() as session:
        operation = (
            await session.scalars(
                select(CreativeOperationModel).where(
                    CreativeOperationModel.id == payload["operation_id"]
                )
            )
        ).one()
        artifacts = list(
            await session.scalars(
                select(CreativeArtifactRefModel).where(
                    CreativeArtifactRefModel.operation_id == operation.id
                )
            )
        )
        checkpoints = list(
            await session.scalars(
                select(CreativeCheckpointModel).where(
                    CreativeCheckpointModel.operation_id == operation.id
                )
            )
        )
        assert operation.status == "succeeded"
        assert len(artifacts) == 3
        assert {item.artifact_type for item in artifacts} == {"recreation_strategy"}
        assert len(checkpoints) == 1

    state = await client.get(f"/cross-cultural-recreations/by-project/{project_id}")
    assert state.status_code == 200
    strategy_candidates = [
        item
        for item in state.json()["artifacts"]
        if item["kind"] == "recreation_strategy"
    ]
    assert len(strategy_candidates) == 3
    assert all(item["status"] == "candidate" for item in strategy_candidates)

    adopted_strategy = await client.post(
        (
            f"/cross-cultural-recreations/by-project/{project_id}/artifacts/"
            f"{strategy_candidates[0]['id']}/adopt"
        ),
        headers={"X-CSRF-Token": csrf},
    )
    assert adopted_strategy.status_code == 200

    async def wait_for_run(run_id: str):
        response = None
        for _ in range(500):
            response = await client.get(
                f"/cross-cultural-recreations/by-project/{project_id}/runs/{run_id}"
            )
            if response.json()["status"] in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.02)
        assert response is not None
        assert response.json()["status"] == "succeeded"

    async def fake_generate_pilot(self, **kwargs):
        del self, kwargs
        return {
            "unit_title": "The Last Call",
            "rationale": "Tests the target-market emotional engine.",
            "target_language_draft": "She answers the final call and chooses the truth.",
            "change_notes": [],
            "gene_trace": [],
            "open_questions": [],
        }

    monkeypatch.setattr(
        CrossCulturalRecreationGenerator,
        "generate_pilot",
        fake_generate_pilot,
    )
    pilot_run = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/pilots",
        params={"background": "true"},
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "recreation-pilot-background", "feedback": None},
    )
    assert pilot_run.status_code == 200
    await wait_for_run(pilot_run.json()["run_id"])
    state = (
        await client.get(f"/cross-cultural-recreations/by-project/{project_id}")
    ).json()
    pilot = next(item for item in state["artifacts"] if item["kind"] == "pilot")
    assert pilot["status"] == "candidate"
    assert (
        await client.post(
            (
                f"/cross-cultural-recreations/by-project/{project_id}/artifacts/"
                f"{pilot['id']}/adopt"
            ),
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200

    async def fake_generate_scale_plan(self, **kwargs):
        del self, kwargs
        return {
            "target_story_bible": {"voice": "first person"},
            "character_migrations": [],
            "work_packages": [
                {
                    "order": 1,
                    "chapter_number": 1,
                    "title": "The Last Call",
                    "source_scope": "opening",
                    "narrative_function": "force the choice",
                    "target_design": "local institutional pressure",
                    "dependencies": [],
                    "protected_genes": ["the final call"],
                    "continuity_inputs": [],
                    "acceptance_criteria": ["the choice remains irreversible"],
                }
            ],
            "continuity_rules": [],
            "quality_gates": [],
            "unresolved_decisions": [],
        }

    monkeypatch.setattr(
        CrossCulturalRecreationGenerator,
        "generate_scale_plan",
        fake_generate_scale_plan,
    )
    scale_run = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/scale-plans",
        params={"background": "true"},
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "recreation-scale-background", "feedback": None},
    )
    assert scale_run.status_code == 200
    await wait_for_run(scale_run.json()["run_id"])
    state = (
        await client.get(f"/cross-cultural-recreations/by-project/{project_id}")
    ).json()
    scale_plan = next(
        item for item in state["artifacts"] if item["kind"] == "scale_plan"
    )
    assert scale_plan["status"] == "candidate"
    assert (
        await client.post(
            (
                f"/cross-cultural-recreations/by-project/{project_id}/artifacts/"
                f"{scale_plan['id']}/adopt"
            ),
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200

    async def fake_generate_production_unit(self, **kwargs):
        del self, kwargs
        return {
            "work_package_key": "1",
            "title": "The Last Call",
            "target_language_draft": "She answers. The institution must answer too.",
            "recreation_rationale": [],
            "gene_trace": [],
            "continuity_updates": [],
            "quality_self_check": [],
            "open_questions": [],
        }

    monkeypatch.setattr(
        CrossCulturalRecreationGenerator,
        "generate_production_unit",
        fake_generate_production_unit,
    )
    production_run = await client.post(
        f"/cross-cultural-recreations/by-project/{project_id}/work-packages/1/drafts",
        params={"background": "true"},
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "recreation-production-background", "feedback": None},
    )
    assert production_run.status_code == 200
    await wait_for_run(production_run.json()["run_id"])
    state = (
        await client.get(f"/cross-cultural-recreations/by-project/{project_id}")
    ).json()
    assert len(state["production_units"]) == 1
    assert state["production_units"][0]["status"] == "candidate"

    operation_ids = {
        pilot_run.json()["operation_id"],
        scale_run.json()["operation_id"],
        production_run.json()["operation_id"],
    }
    artifact_refs = []
    checkpoints = []
    for _ in range(100):
        async with database.session() as session:
            artifact_refs = list(
                await session.scalars(
                    select(CreativeArtifactRefModel).where(
                        CreativeArtifactRefModel.operation_id.in_(operation_ids)
                    )
                )
            )
            checkpoints = list(
                await session.scalars(
                    select(CreativeCheckpointModel).where(
                        CreativeCheckpointModel.operation_id.in_(operation_ids)
                    )
                )
            )
        if len(artifact_refs) == 3 and len(checkpoints) == 3:
            break
        await asyncio.sleep(0.02)
    assert {item.artifact_type for item in artifact_refs} == {
        "pilot",
        "scale_plan",
        "production_unit",
    }, {
        "operation_ids": operation_ids,
        "artifact_refs": [
            (item.operation_id, item.artifact_type, item.artifact_id)
            for item in artifact_refs
        ],
    }
    assert len(checkpoints) == 3


@pytest.mark.asyncio
async def test_login_project_mock_run_sse_billing_and_audit(platform_api) -> None:
    client_a, client_b, database = platform_api
    csrf_a = await login(client_a, "a@example.com")
    await login(client_b, "b@example.com")

    options = await client_a.get("/creative-options/novel")
    assert options.status_code == 200
    visible_genres = {item["key"]: item for item in options.json()["genres"]}
    assert visible_genres["werewolf-romance"]["skill_keys"]
    assert visible_genres["science-fiction"]["label_zh"] == "科幻"
    assert (await client_a.get("/creative-options/translation")).status_code == 422

    project = await client_a.post(
        "/projects",
        headers={"X-CSRF-Token": csrf_a},
        json={"name": "Harbor", "medium": "script"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    assert (await client_b.get("/projects")).json() == []
    assert (
        await client_b.post(
            f"/projects/{project_id}/runs/mock",
            headers={"X-CSRF-Token": client_b.cookies["sf_csrf"]},
            json={"idempotency_key": "cross-tenant"},
        )
    ).status_code == 409

    run = await client_a.post(
        f"/projects/{project_id}/runs/mock",
        headers={"X-CSRF-Token": csrf_a},
        json={"idempotency_key": "first-run", "max_tokens": 100},
    )
    assert run.status_code == 200
    assert run.json()["status"] == "succeeded"
    assert run.json()["billed_tokens"] == 20
    run_id = run.json()["id"]
    replay = await client_a.post(
        f"/projects/{project_id}/runs/mock",
        headers={"X-CSRF-Token": csrf_a},
        json={"idempotency_key": "first-run", "max_tokens": 100},
    )
    assert replay.json() == run.json()

    stream = await client_a.get(f"/runs/{run_id}/events")
    assert stream.status_code == 200
    assert "id: 1\nevent: agent" in stream.text
    assert "id: 2\nevent: terminal" in stream.text
    resumed = await client_a.get(f"/runs/{run_id}/events", headers={"Last-Event-ID": "1"})
    assert "event: agent" not in resumed.text
    assert "id: 2\nevent: terminal" in resumed.text
    assert (await client_b.get(f"/runs/{run_id}/events")).status_code == 404

    async with database.session() as session:
        usage = (await session.scalars(select(TokenUsageModel))).all()
        ledger = (await session.scalars(select(CreditLedgerModel))).all()
        audits = (await session.scalars(select(AuditLogModel))).all()
        assert len(usage) == 1
        assert [item.operation for item in ledger] == ["reserve", "finalize"]
        assert [item.action for item in audits] == ["project.create", "run.mock.complete"]


@pytest.mark.asyncio
async def test_project_deletion_requires_exact_name_and_hides_project(platform_api) -> None:
    client, other_client, database = platform_api
    csrf = await login(client, "a@example.com")
    other_csrf = await login(other_client, "b@example.com")
    response = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "需要谨慎删除的项目", "medium": "novel"},
    )
    project_id = response.json()["id"]

    cross_tenant = await other_client.request(
        "DELETE",
        f"/projects/{project_id}",
        headers={"X-CSRF-Token": other_csrf},
        json={"confirmation_name": "需要谨慎删除的项目"},
    )
    assert cross_tenant.status_code == 404

    mismatch = await client.request(
        "DELETE",
        f"/projects/{project_id}",
        headers={"X-CSRF-Token": csrf},
        json={"confirmation_name": "名称不一致"},
    )
    assert mismatch.status_code == 422
    assert len((await client.get("/projects")).json()) == 1

    deleted = await client.request(
        "DELETE",
        f"/projects/{project_id}",
        headers={"X-CSRF-Token": csrf},
        json={"confirmation_name": "需要谨慎删除的项目"},
    )
    assert deleted.status_code == 204
    assert (await client.get("/projects")).json() == []
    assert (await client.get(f"/projects/{project_id}/models")).status_code == 404

    async with database.session() as session:
        project = await session.get(ProjectModel, project_id)
        assert project is not None
        assert project.deleted_at is not None
        audits = (
            await session.scalars(
                select(AuditLogModel).where(AuditLogModel.resource_id == project_id)
            )
        ).all()
        assert [item.action for item in audits] == ["project.create", "project.delete"]


@pytest.mark.asyncio
async def test_state_changes_require_csrf_and_development_allows_budget_overage(
    platform_api,
) -> None:
    client_a, _, database = platform_api
    csrf = await login(client_a, "a@example.com")
    assert (
        await client_a.post("/projects", json={"name": "No CSRF", "medium": "novel"})
    ).status_code == 403
    project = await client_a.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Novel", "medium": "novel"},
    )
    async with database.session() as session:
        account = (await session.scalars(select(TokenAccountModel))).first()
        assert account is not None
        account.monthly_available = 0
    development_run = await client_a.post(
        f"/projects/{project.json()['id']}/runs/mock",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "no-balance", "max_tokens": 1},
    )
    assert development_run.status_code == 200


@pytest.mark.asyncio
async def test_source_distillation_requires_explicit_external_processing_consent(
    platform_api,
) -> None:
    client, _, database = platform_api
    csrf = await login(client, "a@example.com")
    response = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Source consent", "medium": "novel", "source_mode": "adaptation"},
    )
    project_id = response.json()["id"]
    async with database.session() as session:
        project = await session.get(ProjectModel, project_id)
        assert project is not None
        source = WorkspaceFileModel(
            tenant_id=project.tenant_id,
            project_id=project.id,
            original_name="source.docx",
            storage_name="source.docx",
            media_type="application/docx",
            byte_size=100,
            sha256="a" * 64,
            status=WorkspaceFileStatus.READY,
        )
        session.add(source)
        await session.flush()
        session.add(
            RagChunkModel(
                tenant_id=project.tenant_id,
                project_id=project.id,
                source_file_id=source.id,
                ordinal=0,
                content="A cited source fragment.",
                content_hash="b" * 64,
            )
        )
        source_id = source.id
    started = await client.post(
        f"/projects/{project_id}/source-distillations",
        headers={"X-CSRF-Token": csrf},
        json={"source_file_ids": [source_id], "idempotency_key": "source-consent"},
    )
    assert started.status_code == 200
    distillation_id = started.json()["id"]
    preflight = await client.get(
        f"/projects/{project_id}/source-distillations/{distillation_id}/execution-preflight"
    )
    assert preflight.status_code == 200
    assert preflight.json()["external_processing"] is True
    assert preflight.json()["total_chunks"] == 1

    denied = await client.post(
        f"/projects/{project_id}/source-distillations/{distillation_id}/execute",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "without-consent"},
    )
    assert denied.status_code == 428
    assert "第三方模型 Provider" in denied.json()["detail"]


@pytest.mark.asyncio
async def test_account_summary_and_model_visibility_are_tenant_scoped(platform_api) -> None:
    client_a, client_b, database = platform_api
    csrf = await login(client_a, "a@example.com")
    await login(client_b, "b@example.com")
    project = await client_a.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Account visibility", "medium": "script"},
    )
    async with database.session() as session:
        pro = TierModel(code="pro", name="Pro", rank=20, monthly_token_quota=50_000)
        provider = (
            await session.scalars(select(ProviderModel).where(ProviderModel.key == "mock"))
        ).one()
        session.add(pro)
        await session.flush()
        session.add(
            LanguageModelModel(
                key="mock-pro",
                display_name="Mock Pro",
                provider_id=provider.id,
                agentscope_class="OpenAIChatModel",
                min_tier_id=pro.id,
            )
        )

    summary = await client_a.get("/account/summary")
    assert summary.status_code == 200
    assert summary.json() == {
        "tenant_name": "Studio A",
        "tier_code": "plus",
        "tier_name": "Plus",
        "monthly_price": 0.0,
        "monthly_quota": 10_000,
        "monthly_remaining": 10_000,
        "monthly_used": 0,
        "credits_available": 0,
        "currency": "CNY",
        "period_key": "2026-07",
    }
    models = (await client_a.get(f"/projects/{project.json()['id']}/models")).json()
    assert [(item["key"], item["available"], item["reason"]) for item in models] == [
        ("mock-v1", True, None),
        ("mock-pro", False, "upgrade_required"),
    ]
    assert (await client_b.get(f"/projects/{project.json()['id']}/models")).status_code == 404


@pytest.mark.asyncio
async def test_agent_team_override_is_scoped_audited_and_snapshotted(platform_api) -> None:
    client_a, client_b, database = platform_api
    csrf = await login(client_a, "a@example.com")
    await login(client_b, "b@example.com")
    project = await client_a.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Agent team", "medium": "novel"},
    )
    project_id = project.json()["id"]
    models = (await client_a.get(f"/projects/{project_id}/models")).json()
    updated = await client_a.put(
        f"/projects/{project_id}/agent-team/writer",
        headers={"X-CSRF-Token": csrf},
        json={
            "custom_name": "长篇写作者",
            "soul_override": "保持克制的第三人称限知。",
            "model_id": models[0]["id"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["custom_name"] == "长篇写作者"
    assert (await client_b.get(f"/projects/{project_id}/agent-team")).status_code == 404

    run = await client_a.post(
        f"/projects/{project_id}/runs/mock",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "agent-team-snapshot", "max_tokens": 100},
    )
    assert run.status_code == 200
    async with database.session() as session:
        config = (await session.scalars(select(TenantAgentConfigModel))).one()
        snapshot = (
            await session.scalars(
                select(RuntimeConfigSnapshotModel).where(
                    RuntimeConfigSnapshotModel.run_id == run.json()["id"]
                )
            )
        ).one()
        audits = (
            await session.scalars(
                select(AuditLogModel).where(AuditLogModel.action == "agent_team.update")
            )
        ).all()
    assert snapshot.snapshot["tenant_agent_config_id"] == config.id
    assert snapshot.snapshot["display_name"] == "长篇写作者"
    assert snapshot.snapshot["soul"].endswith("保持克制的第三人称限知。")
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_adaptation_upload_list_delete_and_cross_tenant_isolation(platform_api) -> None:
    client_a, client_b, _ = platform_api
    csrf_a = await login(client_a, "a@example.com")
    await login(client_b, "b@example.com")
    project = await client_a.post(
        "/projects",
        headers={"X-CSRF-Token": csrf_a},
        json={
            "name": "Adaptation",
            "medium": "novel",
            "source_mode": "adaptation",
            "direction": {"premise": "A hidden letter returns."},
        },
    )
    project_id = project.json()["id"]
    uploaded = await client_a.post(
        f"/projects/{project_id}/files",
        headers={"X-CSRF-Token": csrf_a},
        files={"file": ("source.txt", b"A hidden letter returns.", "text/plain")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["status"] == "ready"
    file_id = uploaded.json()["id"]
    assert [
        item["id"] for item in (await client_a.get(f"/projects/{project_id}/files")).json()
    ] == [file_id]
    hits = await client_a.get(f"/projects/{project_id}/rag/search", params={"q": "letter"})
    assert hits.status_code == 200
    assert hits.json()[0]["source_file_id"] == file_id
    assert hits.json()[0]["source_name"] == "source.txt"
    assert "hidden letter" in hits.json()[0]["excerpt"]
    assert (
        await client_b.get(f"/projects/{project_id}/rag/search", params={"q": "letter"})
    ).status_code == 404
    assert (await client_b.get(f"/projects/{project_id}/files")).status_code == 404
    deleted = await client_a.delete(
        f"/projects/{project_id}/files/{file_id}", headers={"X-CSRF-Token": csrf_a}
    )
    assert deleted.status_code == 204
    assert (await client_a.get(f"/projects/{project_id}/files")).json() == []
    assert (
        await client_a.get(f"/projects/{project_id}/rag/search", params={"q": "letter"})
    ).json() == []


@pytest.mark.parametrize(
    ("medium", "source_mode"),
    [
        ("script", "original"),
        ("script", "adaptation"),
        ("novel", "original"),
        ("novel", "adaptation"),
    ],
)
@pytest.mark.asyncio
async def test_all_medium_source_combinations_persist_only_their_domain_skeleton(
    platform_api, medium: str, source_mode: str
) -> None:
    client, _, database = platform_api
    csrf = await login(client, "a@example.com")
    response = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": f"{medium}-{source_mode}",
            "medium": medium,
            "source_mode": source_mode,
            "direction": {"premise": "A durable seed"},
        },
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    async with database.session() as session:
        script_plan = await session.scalar(
            select(ScriptPlanModel).where(ScriptPlanModel.project_id == project_id)
        )
        script_map = await session.scalar(
            select(ScriptStoryMapModel).where(ScriptStoryMapModel.project_id == project_id)
        )
        novel_plan = await session.scalar(
            select(NovelPlanModel).where(NovelPlanModel.project_id == project_id)
        )
        novel_map = await session.scalar(
            select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project_id)
        )
        if medium == "script":
            assert script_plan is not None and script_map is not None
            assert novel_plan is None and novel_map is None
        else:
            assert novel_plan is not None and novel_map is not None
            assert script_plan is None and script_map is None


@pytest.mark.parametrize("source_mode", ["original", "adaptation"])
@pytest.mark.asyncio
async def test_script_api_story_core_blueprint_story_map_writer_full_slice(
    platform_api, source_mode: str, monkeypatch
) -> None:
    client, other_client, database = platform_api
    csrf = await login(client, "a@example.com")
    await login(other_client, "b@example.com")
    project = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": f"Script {source_mode}",
            "medium": "script",
            "source_mode": source_mode,
            "direction": {
                "premise": "A witness receives tomorrow's letter.",
                "volume_one": "1",
                "volume_two": "2",
                "volume_three": "3",
            },
        },
    )
    project_id = project.json()["id"]
    core_request = {
        "idempotency_key": "core-1",
        "drafts": [
            {
                "title": f"Direction {index}",
                "concept": (
                    f"A witness follows a distinct causal route {index}, makes an irreversible "
                    "choice, and pays a visible personal cost before the truth becomes public."
                ),
                "angles": ["desire", "resistance", "relationship", "cost", "choice"],
                "details": {
                    "narrative_engine": ["discovery changes the plan", "choice creates cost"],
                    "viewpoint_anchor": ["limited witness perspective"],
                    "pacing_recipe": ["discovery, escalation, reversal, choice"],
                    "market_judgement": ["clear dramatic engine", "avoid exposition"],
                },
            }
            for index in range(1, 4)
        ],
    }
    core = await client.post(
        f"/script/projects/{project_id}/story-cores/propose",
        headers={"X-CSRF-Token": csrf},
        json=core_request,
    )
    assert core.status_code == 200 and len(core.json()) == 3
    replay = await client.post(
        f"/script/projects/{project_id}/story-cores/propose",
        headers={"X-CSRF-Token": csrf},
        json=core_request,
    )
    assert [item["id"] for item in replay.json()] == [item["id"] for item in core.json()]
    assert (
        await client.post(
            f"/script/projects/{project_id}/story-cores/{core.json()[0]['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    blueprint_candidate = await client.post(
        f"/script/projects/{project_id}/blueprints/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "blueprint-1",
            "anchors": [
                {
                    "id": f"{kind}:{index}",
                    "kind": kind,
                    "name": f"{kind} {index}",
                    "payload": {"description": f"Specific actionable {kind} evidence {index}"},
                }
                for index, kind in enumerate(
                    [
                        "worldview",
                        "worldview",
                        "character",
                        "character",
                        "relationship",
                        "arc",
                        "character_arc",
                        "event",
                        "event",
                        "foreshadow",
                        "foreshadow",
                    ],
                    1,
                )
            ],
        },
    )
    pending_blueprint_state = (await client.get(f"/script/projects/{project_id}/state")).json()
    assert pending_blueprint_state["phase"] == "story_core_adopted"
    assert pending_blueprint_state["blueprint"] is None
    assert pending_blueprint_state["blueprint_candidates"][0]["status"] == "active"
    assert len(pending_blueprint_state["blueprint_candidates"][0]["anchors"]) == 11
    assert (
        await client.post(
            f"/script/projects/{project_id}/blueprints/{blueprint_candidate.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    structure_candidate = await client.post(
        f"/script/projects/{project_id}/story-map/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "expected_version": 1,
            "idempotency_key": "structure-1",
            "episodes": [
                {
                    "id": "episode-1",
                    "ordinal": 1,
                    "title": "Test episode",
                    "scenes": [
                        {
                            "id": f"scene-{index}",
                            "ordinal": index,
                            "title": f"Scene {index}",
                            "duration_seconds_target": 180,
                            "beats": [
                                {
                                    "id": f"beat-{index}",
                                    "objective": f"Scene {index} changes the course of action.",
                                    "anchor_ids": ["character:3", f"event:{8 if index == 1 else 9}"],
                                }
                            ],
                        }
                        for index in range(1, 3)
                    ],
                }
            ],
        },
    )
    pending_structure_state = (await client.get(f"/script/projects/{project_id}/state")).json()
    assert pending_structure_state["phase"] == "blueprint_adopted"
    assert pending_structure_state["story_map"]["episodes"] == []
    assert pending_structure_state["story_map_candidates"][0]["status"] == "active"
    assert pending_structure_state["story_map_candidates"][0]["episodes"][0]["scenes"]
    edited_episodes = pending_structure_state["story_map_candidates"][0]["episodes"]
    edited_episodes[0]["scenes"][0]["title"] = "重新排序后的触发事件"
    revised_structure = await client.post(
        f"/script/projects/{project_id}/story-map/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "expected_version": pending_structure_state["story_map"]["version"],
            "episodes": edited_episodes,
            "idempotency_key": "structure-revised",
        },
    )
    assert revised_structure.status_code == 200
    structure_candidate = revised_structure
    revised_structure_state = (await client.get(f"/script/projects/{project_id}/state")).json()
    assert (
        sum(item["status"] == "active" for item in revised_structure_state["story_map_candidates"])
        == 1
    )
    assert any(
        item["status"] == "expired" for item in revised_structure_state["story_map_candidates"]
    )
    active_structure = next(
        item
        for item in revised_structure_state["story_map_candidates"]
        if item["status"] == "active"
    )
    assert active_structure["episodes"][0]["scenes"][0]["title"] == "重新排序后的触发事件"
    assert (
        await client.post(
            f"/script/projects/{project_id}/story-map/{structure_candidate.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200

    async def generated_scene(*_args, **_kwargs) -> AgentRuntimeResult:
        return AgentRuntimeResult(
            text=(
                '{"blocks":['
                '{"type":"slugline","text":"INT. TEST ROOM - DAY"},'
                '{"type":"action","text":"The witness opens tomorrow’s letter."},'
                '{"type":"character","text":"WITNESS"},'
                '{"type":"dialogue","text":"This changes everything."}'
                "]}"
            ),
            runtime="test",
            model_key="test-writer",
            input_tokens=1,
            output_tokens=1,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
        )

    monkeypatch.setattr(AgentRuntime, "generate", generated_scene)
    queued_scene = await client.post(
        f"/script/projects/{project_id}/scenes/scene-1/generate?background=true",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "scene-1-draft"},
    )
    assert queued_scene.status_code == 200
    assert queued_scene.json()["operation_id"]
    assert queued_scene.json()["creative_session_id"]
    scene_run_id = queued_scene.json()["run_id"]
    scene_run_state = None
    for _ in range(100):
        scene_run_state = await client.get(
            f"/script/projects/{project_id}/runs/{scene_run_id}"
        )
        if scene_run_state.json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.05)
    assert scene_run_state is not None
    assert scene_run_state.json()["status"] == "succeeded"
    assert scene_run_state.json()["operation_status"] == "succeeded"
    generated_state = (await client.get(f"/script/projects/{project_id}/state")).json()
    document_candidate = next(
        item for item in generated_state["documents"] if item["scene_id"] == "scene-1"
    )
    assert (
        await client.post(
            f"/script/projects/{project_id}/scenes/scene-1/revisions/{document_candidate['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    async with database.session() as session:
        scene_runs = list(
            await session.scalars(
                select(ProjectRunModel).where(
                    ProjectRunModel.project_id == project_id,
                    ProjectRunModel.idempotency_key
                    == f"script-scene:{project_id}:scene-1:scene-1-draft",
                )
            )
        )
        scene_operation = await session.get(
            CreativeOperationModel,
            queued_scene.json()["operation_id"],
        )
        scene_stages = list(
            await session.scalars(
                select(CreativeStageRunModel).where(
                    CreativeStageRunModel.operation_id == scene_operation.id
                )
            )
        )
        scene_artifacts = list(
            await session.scalars(
                select(CreativeArtifactRefModel).where(
                    CreativeArtifactRefModel.operation_id == scene_operation.id
                )
            )
        )
        scene_checkpoints = list(
            await session.scalars(
                select(CreativeCheckpointModel).where(
                    CreativeCheckpointModel.operation_id == scene_operation.id
                )
            )
        )
    assert len(scene_runs) == 1
    assert scene_operation.command == "script.scene.generate"
    assert len(scene_stages) == len(scene_artifacts) == len(scene_checkpoints) == 1
    assert scene_artifacts[0].artifact_type == "scene_revision"
    second_document = await client.post(
        f"/script/projects/{project_id}/scenes/scene-2/generate",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "scene-2-draft"},
    )
    assert (
        await client.post(
            f"/script/projects/{project_id}/scenes/scene-2/revisions/{second_document.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    state = (await client.get(f"/script/projects/{project_id}/state")).json()
    assert state["phase"] == "writing"
    assert state["blueprint"]["anchors"]
    assert state["story_map"]["episodes"][0]["scenes"][0]["id"] == "scene-1"
    assert len(state["documents"]) == 2
    assert all(item["status"] == "adopted" for item in state["documents"])
    assert state["documents"][0]["blocks"][0]["type"] == "slugline"
    finding = await client.post(
        f"/projects/{project_id}/units/scene-1/review/scan",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "scan-scene-1"},
    )
    assert finding.status_code == 200 and finding.json()["source"] == "ai"
    assert (await other_client.get(f"/projects/{project_id}/findings")).status_code == 404
    accepted = await client.post(
        f"/projects/{project_id}/findings/{finding.json()['id']}/accept",
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    revised = (await client.get(f"/script/projects/{project_id}/state")).json()
    assert any(
        item["scene_id"] == "scene-1"
        and item["revision_number"] == 2
        and item["status"] == "adopted"
        for item in revised["documents"]
    )
    rolled_back = await client.post(
        f"/projects/{project_id}/findings/{finding.json()['id']}/rollback",
        headers={"X-CSRF-Token": csrf},
    )
    assert rolled_back.status_code == 200
    rollback_state = (await client.get(f"/script/projects/{project_id}/state")).json()
    assert any(
        item["scene_id"] == "scene-1"
        and item["revision_number"] == 3
        and item["status"] == "adopted"
        for item in rollback_state["documents"]
    )
    timeline = (await client.get(f"/projects/{project_id}/review/timeline")).json()
    assert [item["payload"]["action"] for item in timeline[:3]] == [
        "review_finding.rollback",
        "review_finding.accept",
        "review_finding.create",
    ]
    current = next(
        item
        for item in rollback_state["documents"]
        if item["scene_id"] == "scene-1" and item["status"] == "adopted"
    )
    slugline = next(item for item in current["blocks"] if item["type"] == "slugline")
    assert (
        await client.post(
            f"/script/projects/{project_id}/scenes/scene-1/selection-edits",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision_id": current["id"],
                "element_id": slugline["para_id"],
                "excerpt": slugline["text"][:4],
                "operation": "polish",
                "idempotency_key": "reject-script-structural-edit",
            },
        )
    ).status_code == 409
    action = next(item for item in current["blocks"] if item["type"] == "action")
    edit_payload = {
        "revision_id": current["id"],
        "element_id": action["para_id"],
        "excerpt": action["text"][:4],
        "operation": "polish",
        "instruction": "更有潜台词",
        "idempotency_key": "script-selection-edit",
    }
    edit = await client.post(
        f"/script/projects/{project_id}/scenes/scene-1/selection-edits",
        headers={"X-CSRF-Token": csrf},
        json=edit_payload,
    )
    replay_edit = await client.post(
        f"/script/projects/{project_id}/scenes/scene-1/selection-edits",
        headers={"X-CSRF-Token": csrf},
        json=edit_payload,
    )
    assert edit.status_code == 200 and edit.json()["id"] == replay_edit.json()["id"]
    assert edit.json()["diff"]["before"] != edit.json()["diff"]["after"]
    assert (
        await client.post(
            f"/script/projects/{project_id}/scenes/scene-1/revisions/{edit.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/script/projects/{project_id}/scenes/scene-1/selection-edits",
            headers={"X-CSRF-Token": csrf},
            json={**edit_payload, "idempotency_key": "stale-script-selection"},
        )
    ).status_code == 409
    assert (await other_client.get(f"/script/projects/{project_id}/state")).status_code == 404


@pytest.mark.parametrize("source_mode", ["original", "adaptation"])
@pytest.mark.asyncio
async def test_novel_api_full_slice_is_independent_and_tenant_scoped(
    platform_api, source_mode: str
) -> None:
    client, other_client, database = platform_api
    csrf = await login(client, "a@example.com")
    await login(other_client, "b@example.com")
    project = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": f"Novel {source_mode}",
            "medium": "novel",
            "source_mode": source_mode,
                "direction": {
                    "premise": "一封迟到二十年的信重新出现。",
                    "chapter_target_words": "1375",
                    "volume_one": "1",
                    "volume_two": "12",
                },
        },
    )
    project_id = project.json()["id"]
    cores = await client.post(
        f"/novel/projects/{project_id}/story-cores/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "core",
            "drafts": [
                {
                    "title": f"方向 {index}",
                    "premise": f"一封迟到二十年的信重新出现，并推动第 {index} 种因果完整的人物选择。",
                    "point_of_view": "第三人称限知",
                    "narrative_constraints": ["人物感知承载信息"],
                    "angles": ["欲望", "阻力", "关系", "代价", "结局"],
                }
                for index in range(1, 4)
            ],
        },
    )
    assert cores.status_code == 200 and len(cores.json()) == 3
    assert "script_format" not in cores.json()[0]
    assert (
        await client.post(
            f"/novel/projects/{project_id}/story-cores/{cores.json()[0]['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    blueprint = await client.post(
        f"/novel/projects/{project_id}/blueprints/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "idempotency_key": "blueprint",
            "anchors": [
                {
                    "id": f"{kind}:{index}",
                    "kind": kind,
                    "name": f"{kind} anchor {index}",
                    "payload": {"description": f"Actionable {kind} detail {index}"},
                }
                for index, kind in enumerate(
                    [
                        "world",
                        "world",
                        "character",
                        "character",
                        "character",
                        "relationship",
                        "relationship",
                        "character_arc",
                        "character_arc",
                        "plot",
                        "foreshadow",
                        "motif",
                    ],
                    start=1,
                )
            ],
        },
    )
    assert blueprint.status_code == 200
    pending_blueprint_state = (await client.get(f"/novel/projects/{project_id}/state")).json()
    assert pending_blueprint_state["phase"] == "story_core_adopted"
    assert pending_blueprint_state["blueprint"] is None
    assert pending_blueprint_state["blueprint_candidates"][0]["status"] == "active"
    assert len(pending_blueprint_state["blueprint_candidates"][0]["anchors"]) == 12
    assert (
        await client.post(
            f"/novel/projects/{project_id}/blueprints/{blueprint.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    structure = await client.post(
        f"/novel/projects/{project_id}/story-map/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "expected_version": 1,
            "idempotency_key": "structure",
            "volumes": [
                {
                    "id": "volume-1",
                    "ordinal": 1,
                    "title": "测试卷",
                    "chapters": [
                        {
                            "id": f"chapter-{index}",
                            "ordinal": index,
                            "title": f"第 {index} 章",
                            "target_words": 1375,
                            "point_of_view": "第三人称限知",
                            "beats": [
                                {
                                    "id": f"beat-{index}",
                                    "objective": f"第 {index} 章发生不可逆行动。",
                                        "anchor_ids": [
                                            "character:3",
                                            "plot:10" if index % 2 else "foreshadow:11",
                                        ],
                                }
                            ],
                        }
                        for index in range(1, 13)
                    ],
                }
            ],
        },
    )
    assert structure.status_code == 200
    pending_structure_state = (await client.get(f"/novel/projects/{project_id}/state")).json()
    assert pending_structure_state["phase"] == "blueprint_adopted"
    assert pending_structure_state["story_map"]["volumes"] == []
    assert pending_structure_state["story_map_candidates"][0]["status"] == "active"
    assert pending_structure_state["story_map_candidates"][0]["volumes"][0]["chapters"]
    assert {
        chapter["target_words"]
        for chapter in pending_structure_state["story_map_candidates"][0]["volumes"][0][
            "chapters"
        ]
    } == {1375}
    edited_volumes = pending_structure_state["story_map_candidates"][0]["volumes"]
    edited_volumes[0]["chapters"][0]["title"] = "迟来的第一章"
    revised_structure = await client.post(
        f"/novel/projects/{project_id}/story-map/propose",
        headers={"X-CSRF-Token": csrf},
        json={
            "expected_version": pending_structure_state["story_map"]["version"],
            "volumes": edited_volumes,
            "idempotency_key": "structure-revised",
        },
    )
    assert revised_structure.status_code == 200
    structure = revised_structure
    revised_structure_state = (await client.get(f"/novel/projects/{project_id}/state")).json()
    assert (
        sum(item["status"] == "active" for item in revised_structure_state["story_map_candidates"])
        == 1
    )
    assert any(
        item["status"] == "expired" for item in revised_structure_state["story_map_candidates"]
    )
    active_structure = next(
        item
        for item in revised_structure_state["story_map_candidates"]
        if item["status"] == "active"
    )
    assert active_structure["volumes"][0]["chapters"][0]["title"] == "迟来的第一章"
    assert (
        await client.post(
            f"/novel/projects/{project_id}/story-map/{structure.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    for chapter_id in ("chapter-1", "chapter-2"):
        draft = await client.post(
            f"/novel/projects/{project_id}/chapters/{chapter_id}/generate",
            headers={"X-CSRF-Token": csrf},
            json={"idempotency_key": f"{chapter_id}-draft"},
        )
        assert draft.status_code == 200
        adopted = await client.post(
            f"/novel/projects/{project_id}/chapters/{chapter_id}/revisions/{draft.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
        assert adopted.status_code == 200
    queued = await client.post(
        f"/novel/projects/{project_id}/chapters/chapter-3/generate?background=true",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "chapter-3-background"},
    )
    assert queued.status_code == 200
    assert queued.json()["operation_id"]
    assert queued.json()["creative_session_id"]
    run_id = queued.json()["run_id"]
    run_state = None
    # The full integration suite exercises several background pipelines before
    # this case. Give the public run endpoint enough wall-clock time to expose
    # its terminal state without coupling the assertion to local CPU load.
    for _ in range(200):
        run_state = await client.get(f"/novel/projects/{project_id}/runs/{run_id}")
        if run_state.json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.05)
    assert run_state is not None
    assert run_state.json()["status"] == "succeeded"
    assert run_state.json()["operation_status"] == "succeeded"
    runs = []
    operation = None
    stages = []
    artifacts = []
    checkpoints = []
    for _ in range(100):
        async with database.session() as session:
            runs = list(
                await session.scalars(
                    select(ProjectRunModel).where(
                            ProjectRunModel.project_id == project_id,
                            ProjectRunModel.idempotency_key
                            == (
                                f"novel-chapter:{project_id}:chapter-3:"
                                "chapter-3-background"
                            ),
                    )
                )
            )
            operation = await session.get(
                CreativeOperationModel,
                queued.json()["operation_id"],
            )
            stages = list(
                await session.scalars(
                    select(CreativeStageRunModel).where(
                        CreativeStageRunModel.operation_id == operation.id
                    )
                )
            )
            artifacts = list(
                await session.scalars(
                    select(CreativeArtifactRefModel).where(
                        CreativeArtifactRefModel.operation_id == operation.id
                    )
                )
            )
            checkpoints = list(
                await session.scalars(
                    select(CreativeCheckpointModel).where(
                        CreativeCheckpointModel.operation_id == operation.id
                    )
                )
            )
        if len(stages) == len(artifacts) == len(checkpoints) == 1:
            break
        await asyncio.sleep(0.02)
    assert len(runs) == 1
    assert operation is not None
    assert operation.command == "novel.chapter.generate"
    assert len(stages) == len(artifacts) == len(checkpoints) == 1
    assert artifacts[0].artifact_type == "chapter_revision"
    state = (await client.get(f"/novel/projects/{project_id}/state")).json()
    assert state["phase"] == "writing"
    assert len(state["story_map"]["volumes"][0]["chapters"]) == 12
    assert {item["chapter_id"] for item in state["documents"]} == {
        "chapter-1",
        "chapter-2",
        "chapter-3",
    }
    assert all(item["blocks"][0]["type"] == "heading" for item in state["documents"])
    finding = await client.post(
        f"/projects/{project_id}/units/chapter-1/review/scan",
        headers={"X-CSRF-Token": csrf},
        json={"idempotency_key": "scan-chapter-1"},
    )
    assert finding.status_code == 200 and finding.json()["source"] == "ai"
    accepted = await client.post(
        f"/projects/{project_id}/findings/{finding.json()['id']}/accept",
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    filtered = await client.get(
        f"/projects/{project_id}/findings?severity=major&source=ai&status=accepted"
    )
    assert len(filtered.json()) == 1
    revised = (await client.get(f"/novel/projects/{project_id}/state")).json()
    assert any(
        item["chapter_id"] == "chapter-1"
        and item["revision_number"] == 2
        and item["status"] == "adopted"
        for item in revised["documents"]
    )
    chapter_two = next(
        item
        for item in revised["documents"]
        if item["chapter_id"] == "chapter-2" and item["status"] == "adopted"
    )
    prose = next(item for item in chapter_two["blocks"] if item["type"] == "prose")
    anchor = revised["blueprint"]["anchors"][0]
    human = await client.post(
        f"/projects/{project_id}/findings",
        headers={"X-CSRF-Token": csrf},
        json={
            "unit_id": "chapter-2",
            "base_revision_id": chapter_two["id"],
            "element_id": prose["block_id"],
            "original_excerpt": prose["text"][:8],
            "domain": "character",
            "severity": "minor",
            "anchor_type": anchor["kind"],
            "anchor_id": anchor["id"],
            "diagnosis": "人工标注的节奏问题。",
            "suggestion": "稍作停顿。",
            "suggested_patch": {"expected_text": prose["text"], "replacement": [prose]},
            "idempotency_key": "human-note",
        },
    )
    assert human.status_code == 200 and human.json()["source"] == "human"
    dismissed = await client.post(
        f"/projects/{project_id}/findings/{human.json()['id']}/dismiss",
        headers={"X-CSRF-Token": csrf},
    )
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    rolled_back = await client.post(
        f"/projects/{project_id}/findings/{finding.json()['id']}/rollback",
        headers={"X-CSRF-Token": csrf},
    )
    assert rolled_back.status_code == 200
    rollback_state = (await client.get(f"/novel/projects/{project_id}/state")).json()
    assert any(
        item["chapter_id"] == "chapter-1"
        and item["revision_number"] == 3
        and item["status"] == "adopted"
        for item in rollback_state["documents"]
    )
    assert len((await client.get(f"/projects/{project_id}/review/timeline")).json()) >= 5
    current = next(
        item
        for item in rollback_state["documents"]
        if item["chapter_id"] == "chapter-1" and item["status"] == "adopted"
    )
    heading = next(item for item in current["blocks"] if item["type"] == "heading")
    assert (
        await client.post(
            f"/novel/projects/{project_id}/chapters/chapter-1/selection-edits",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision_id": current["id"],
                "element_id": heading["block_id"],
                "excerpt": heading["text"][:4],
                "operation": "polish",
                "idempotency_key": "reject-novel-structural-edit",
            },
        )
    ).status_code == 409
    prose = next(item for item in current["blocks"] if item["type"] == "prose")
    edit = await client.post(
        f"/novel/projects/{project_id}/chapters/chapter-1/selection-edits",
        headers={"X-CSRF-Token": csrf},
        json={
            "revision_id": current["id"],
            "element_id": prose["block_id"],
            "excerpt": prose["text"][:5],
            "operation": "expand",
            "instruction": "增加内心感受",
            "idempotency_key": "novel-selection-edit",
        },
    )
    assert edit.status_code == 200 and edit.json()["medium"] == "novel"
    assert edit.json()["diff"]["before"] != edit.json()["diff"]["after"]
    assert (
        await client.post(
            f"/novel/projects/{project_id}/chapters/chapter-1/revisions/{edit.json()['id']}/adopt",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    assert (await other_client.get(f"/novel/projects/{project_id}/state")).status_code == 404


@pytest.mark.asyncio
async def test_dock_projection_stream_wait_confirm_reconnect_and_billing_idempotency(
    platform_api,
) -> None:
    client, other, database = platform_api
    csrf = await login(client, "a@example.com")
    await login(other, "b@example.com")
    project = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Dock", "medium": "novel"},
    )
    project_id = project.json()["id"]
    disconnected = (await client.get(f"/projects/{project_id}/agents/writer/transparency")).json()
    assert disconnected["connected"] is False and disconnected["context_percent"] is None
    async with database.session() as session:
        project_record = await session.get(ProjectModel, project_id)
        session.add_all(
            [
                AgentStateModel(
                    tenant_id=project_record.tenant_id,
                    project_id=project_id,
                    role_key="writer",
                    serialized_state={},
                    context_tokens=900,
                    context_limit=1000,
                ),
                MemoryEntryModel(
                    tenant_id=project_record.tenant_id,
                    project_id=project_id,
                    role_key="writer",
                    relative_path=f"{project_id}/Memory/writer/decision.md",
                    content_hash="a" * 64,
                ),
            ]
        )
    connected = (await client.get(f"/projects/{project_id}/agents/writer/transparency")).json()
    assert connected["connected"] is True
    assert connected["context_percent"] == 90.0 and connected["memory_entries"] == 1
    message = {
        "content": "请检查当前章节的连续性",
        "idempotency_key": "dock-message-1",
        "quote": {"operation": "润色", "excerpt": "迟来的信"},
    }
    completed = await client.post(
        f"/projects/{project_id}/agents/writer/messages",
        headers={"X-CSRF-Token": csrf},
        json=message,
    )
    completed_payload = completed.json()
    assert completed.status_code == 200 and completed_payload["status"] == "succeeded"
    assert completed_payload["operation_status"] == "succeeded"
    assert completed_payload["operation_id"]
    assert completed_payload["creative_session_id"]
    run_id = completed_payload["id"]
    replay = await client.post(
        f"/projects/{project_id}/agents/writer/messages",
        headers={"X-CSRF-Token": csrf},
        json=message,
    )
    assert replay.json()["id"] == run_id
    assert replay.json()["operation_id"] == completed_payload["operation_id"]
    stream = await client.get(f"/projects/{project_id}/agents/writer/stream?run_id={run_id}")
    assert stream.status_code == 200
    for block in ("data", "text"):
        assert f'"block":"{block}"' in stream.text
    assert '"block":"thinking"' not in stream.text
    assert '"block":"tool"' not in stream.text
    assert '"project_name":"Dock"' in stream.text
    assert '"story_units":0' in stream.text
    assert "真实项目状态" in stream.text
    resumed = await client.get(
        f"/projects/{project_id}/agents/writer/stream?run_id={run_id}&after_id=2"
    )
    assert '"project_name":"Dock"' not in resumed.text
    events = (await client.get(f"/projects/{project_id}/events")).json()
    assert all(
        item["event_id"] == item["id"]
        and item["schema_version"] == 1
        and item["actor"]["type"]
        and item["aggregate"]["id"]
        and item["correlation_id"]
        and item["idempotency_key"]
        and item["occurred_at"]
        for item in events
    )
    assert any(item["type"] == "chat" and item["payload"].get("quote") for item in events)
    assert any(
        item["type"] == "node"
        and item["payload"].get("title") == "项目上下文已构建"
        and item["count"] > 0
        for item in events
    )
    compression = next(
        item for item in events if item["payload"].get("action") == "context.compress"
    )
    assert compression["type"] == "system"
    assert compression["payload"]["preserved"] == ["创作决策", "用户偏好", "项目禁用词"]
    assert compression["payload"]["memory_deep_link"].startswith("/admin/memory")
    compressed_status = (
        await client.get(f"/projects/{project_id}/agents/writer/transparency")
    ).json()
    assert compressed_status["connected"] is True
    assert compressed_status["context_tokens"] > 0
    cursor = events[-2]["id"]
    incremental = (await client.get(f"/projects/{project_id}/events?after_id={cursor}")).json()
    assert incremental and incremental[-1]["id"] == events[-1]["id"]
    assert (await other.get(f"/projects/{project_id}/events")).status_code == 404

    waiting = await client.post(
        f"/projects/{project_id}/agents/writer/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "写入工作区",
            "idempotency_key": "dock-wait",
            "requires_confirmation": True,
        },
    )
    waiting_payload = waiting.json()
    assert waiting_payload["status"] == "waiting"
    assert waiting_payload["operation_status"] == "waiting_for_decision"
    assert waiting_payload["decision_request_id"]
    waiting_id = waiting_payload["id"]
    recovered = (await client.get(f"/projects/{project_id}/runs")).json()
    assert any(
        item["id"] == waiting_id
        and item["status"] == "waiting"
        and item["operation_id"] == waiting_payload["operation_id"]
        and item["operation_status"] == "waiting_for_decision"
        for item in recovered
    )
    decision = {"run_id": waiting_id, "approved": True, "idempotency_key": "approve-1"}
    confirmed = await client.post(
        f"/projects/{project_id}/agents/writer/confirm",
        headers={"X-CSRF-Token": csrf},
        json=decision,
    )
    repeated = await client.post(
        f"/projects/{project_id}/agents/writer/confirm",
        headers={"X-CSRF-Token": csrf},
        json=decision,
    )
    assert confirmed.json()["status"] == repeated.json()["status"] == "succeeded"
    assert confirmed.json()["operation_status"] == "succeeded"
    cancellable = await client.post(
        f"/projects/{project_id}/agents/writer/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "等待后取消",
            "idempotency_key": "dock-cancel",
            "requires_confirmation": True,
        },
    )
    cancelled = await client.post(
        f"/projects/{project_id}/runs/{cancellable.json()['id']}/cancel",
        headers={"X-CSRF-Token": csrf},
    )
    assert cancelled.json()["status"] == "cancelled"
    events_after_cancel = (await client.get(f"/projects/{project_id}/events")).json()
    assert any(
        item["type"] == "system" and item["payload"].get("status") == "cancelled"
        for item in events_after_cancel
    )
    async with database.session() as session:
        usage = list(
            await session.scalars(
                select(TokenUsageModel).where(TokenUsageModel.project_id == project_id)
            )
        )
        reservations = list(
            await session.scalars(
                select(UsageReservationModel).where(
                    UsageReservationModel.tenant_id == project_record.tenant_id
                )
            )
        )
        assert usage == []
        scoped = [
            item
            for item in reservations
            if item.run_id in {run_id, waiting_id, cancellable.json()["id"]}
        ]
        assert len(scoped) == 3
        assert all(item.status == "released" for item in scoped)
        audits = list(
            await session.scalars(
                select(MemoryAuditModel).where(
                    MemoryAuditModel.project_id == project_id,
                    MemoryAuditModel.operation == "compress",
                )
            )
        )
        assert len(audits) == 1


@pytest.mark.asyncio
async def test_dock_timeout_has_stable_http_run_and_terminal_event(
    platform_api, monkeypatch
) -> None:
    client, _, database = platform_api
    csrf = await login(client, "a@example.com")
    project = await client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Timeout", "medium": "novel"},
    )
    project_id = project.json()["id"]

    async def connected_status(self, *, tenant_id: str, project_id: str):
        del self, tenant_id, project_id
        role = {"connected": True, "model_key": "test", "provider_key": "test"}
        return {
            "connected": True,
            "roles": {
                "director": role,
                "architect": role,
                "writer": role,
                "reviewer": role,
            },
            "active_runs": [],
        }

    async def timed_out(self, **kwargs):
        del self, kwargs
        raise AgentRuntimeTimeoutError("Agent runtime exceeded 1 seconds")

    monkeypatch.setattr(AgentRuntime, "status", connected_status)
    monkeypatch.setattr(AgentRuntime, "generate", timed_out)

    response = await client.post(
        f"/projects/{project_id}/agents/writer/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "继续写作",
            "idempotency_key": "dock-timeout",
        },
    )

    assert response.status_code == 504
    runs = (await client.get(f"/projects/{project_id}/runs")).json()
    assert runs[0]["status"] == "failed"
    run_id = runs[0]["id"]
    stream = await client.get(
        f"/projects/{project_id}/agents/writer/stream",
        params={"run_id": run_id},
    )
    assert "event: terminal" in stream.text
    assert '"error_code":"agent_runtime_timeout"' in stream.text
    async with database.session() as session:
        reservation = (
            await session.scalars(
                select(UsageReservationModel).where(
                    UsageReservationModel.run_id == run_id
                )
            )
        ).one()
        assert reservation.status == "released"
