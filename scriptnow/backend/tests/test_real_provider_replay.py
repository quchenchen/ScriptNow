from pathlib import Path

import pytest

from scriptnow.diagnostics.real_provider_replay import (
    RealProviderReplayError,
    _provider_proof,
    replay_persisted_four_domain_flows,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentTemplateVersionModel,
    LanguageModelModel,
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    ProviderModel,
    RunStatus,
    RuntimeConfigSnapshotModel,
    TenantModel,
    TierModel,
)

GOLDEN_ROOT = Path(__file__).parents[1] / "golden" / "creative-flow-v1"


@pytest.mark.asyncio
async def test_real_provider_proof_rejects_mock_runtime() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            tenant = TenantModel(name="Replay")
            tier = TierModel(code="test", name="Test", rank=1)
            provider = ProviderModel(key="mock", name="Mock")
            session.add_all([tenant, tier, provider])
            await session.flush()
            model = LanguageModelModel(
                key="mock-v1",
                display_name="Mock",
                provider_id=provider.id,
                agentscope_class="OpenAIChatModel",
                min_tier_id=tier.id,
            )
            project = ProjectModel(
                tenant_id=tenant.id,
                name="Novel",
                medium=ProjectMedium.NOVEL,
            )
            session.add_all([project, model])
            await session.flush()
            version = AgentTemplateVersionModel(
                role_key="writer",
                version=1,
                soul="write",
                default_model_id=model.id,
                policy={},
            )
            run = ProjectRunModel(
                tenant_id=tenant.id,
                project_id=project.id,
                idempotency_key="mock-proof",
                status=RunStatus.SUCCEEDED,
            )
            session.add_all([version, run])
            await session.flush()
            session.add(
                RuntimeConfigSnapshotModel(
                    run_id=run.id,
                    tenant_id=tenant.id,
                    template_version_id=version.id,
                    snapshot={"provider_key": "mock", "model_key": "mock-v1"},
                    fingerprint="f" * 64,
                )
            )
            await session.flush()

            with pytest.raises(RealProviderReplayError, match="mock runtime"):
                await _provider_proof(session, project=project)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_four_domain_replay_requires_complete_mapping() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            with pytest.raises(RealProviderReplayError, match="mapping is invalid"):
                await replay_persisted_four_domain_flows(
                    session,
                    golden_root=GOLDEN_ROOT,
                    project_ids={"novel": "only-one"},
                )
    finally:
        await database.dispose()
