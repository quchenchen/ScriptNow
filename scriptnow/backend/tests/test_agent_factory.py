from uuid import uuid4

import pytest

from scriptnow.platform.agent_factory import AgentFactory, RuntimeConfigError
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentTemplateVersionModel,
    LanguageModelModel,
    ProjectModel,
    ProjectRunModel,
    ProviderModel,
    ProviderStatus,
    SourceDistillationModel,
    SourceProfileModel,
    TenantModel,
    TierModel,
)


@pytest.fixture
async def factory_data() -> tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        plus = TierModel(code="plus", name="Plus", rank=10, version=4)
        provider = ProviderModel(key="mock", name="Mock", status=ProviderStatus.CONNECTED)
        tenant = TenantModel(name="Studio", tier="plus")
        session.add_all([plus, provider, tenant])
        await session.flush()
        model = LanguageModelModel(
            key="mock-v1",
            display_name="Mock V1",
            provider_id=provider.id,
            agentscope_class="OpenAIChatModel",
            min_tier_id=plus.id,
            version=3,
        )
        session.add(model)
        await session.flush()
        template = AgentTemplateVersionModel(
            role_key="writer",
            version=7,
            soul="Write with restraint.",
            default_model_id=model.id,
            tool_keys=["workspace.read"],
            policy={"max_iters": 8},
            published=True,
        )
        session.add(template)
        await session.flush()
    yield AgentFactory(database), database, tenant, template
    await database.dispose()


@pytest.mark.asyncio
async def test_snapshot_is_idempotent_and_immutable_after_admin_changes(
    factory_data: tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel],
) -> None:
    factory, database, tenant, template = factory_data
    run_id = str(uuid4())
    first = await factory.snapshot_for_run(tenant_id=tenant.id, run_id=run_id, role_key="writer")
    async with database.session() as session:
        stored_template = await session.get(AgentTemplateVersionModel, template.id)
        assert stored_template is not None
        stored_template.soul = "Changed after run start."
        stored_template.policy = {"max_iters": 99}

    repeated = await factory.snapshot_for_run(tenant_id=tenant.id, run_id=run_id, role_key="writer")
    assert repeated == first
    assert repeated.values["soul"] == "Write with restraint."
    assert repeated.values["policy"] == {"max_iters": 8}
    assert "credential" not in repeated.values


@pytest.mark.asyncio
async def test_unavailable_selected_model_is_rejected(
    factory_data: tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel],
) -> None:
    factory, database, tenant, _ = factory_data
    async with database.session() as session:
        max_tier = TierModel(code="max", name="Max", rank=30)
        provider = ProviderModel(key="offline", name="Offline", status=ProviderStatus.ERROR)
        session.add_all([max_tier, provider])
        await session.flush()
        unavailable = LanguageModelModel(
            key="locked",
            display_name="Locked",
            provider_id=provider.id,
            agentscope_class="OpenAIChatModel",
            min_tier_id=max_tier.id,
        )
        session.add(unavailable)
        await session.flush()

    with pytest.raises(RuntimeConfigError, match="not available"):
        await factory.snapshot_for_run(
            tenant_id=tenant.id,
            run_id=str(uuid4()),
            role_key="writer",
            selected_model_id=unavailable.id,
        )


@pytest.mark.asyncio
async def test_snapshot_freezes_domain_skills(
    factory_data: tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel],
) -> None:
    factory, database, tenant, _ = factory_data
    async with database.session() as session:
        project = ProjectModel(tenant_id=tenant.id, name="Novel", medium="novel")
        session.add(project)
        await session.flush()
        run = ProjectRunModel(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key=f"skills-{uuid4()}",
        )
        session.add(run)
        await session.flush()
        run_id = run.id
    snapshot = await factory.snapshot_for_run(tenant_id=tenant.id, run_id=run_id, role_key="writer")
    assert snapshot.values["skill_domain"] == "novel"
    assert {
        "novel-write",
        "project-diagnose",
        "novel-continuity-check",
        "novel-emotional-depth",
        "novel-pacing-check",
    } <= set(snapshot.values["skill_keys"])
    assert snapshot.values["skill_catalog_fingerprint"]


@pytest.mark.asyncio
async def test_snapshot_can_disable_skills_for_contract_repair(
    factory_data: tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel],
) -> None:
    factory, database, tenant, _ = factory_data
    async with database.session() as session:
        project = ProjectModel(tenant_id=tenant.id, name="Script", medium="script")
        session.add(project)
        await session.flush()
        run = ProjectRunModel(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key=f"contract-repair-{uuid4()}",
        )
        session.add(run)
        await session.flush()
        run_id = run.id

    snapshot = await factory.snapshot_for_run(
        tenant_id=tenant.id,
        run_id=run_id,
        role_key="writer",
        skills_enabled=False,
    )

    assert snapshot.values["skill_domain"] == "script"
    assert snapshot.values["skill_keys"] == []
    assert snapshot.values["skill_plan"] is None


@pytest.mark.asyncio
async def test_snapshot_selects_style_skill_from_project_creative_profile(
    factory_data: tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel],
) -> None:
    factory, database, tenant, _ = factory_data
    async with database.session() as session:
        project = ProjectModel(
            tenant_id=tenant.id,
            name="电光美人",
            medium="novel",
            direction={
                "genre": "科幻",
                "themes": ["人机情感", "硅基生命"],
                "style": "克制",
                "narrative_structure": "save-the-cat",
            },
        )
        session.add(project)
        await session.flush()
        run = ProjectRunModel(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key=f"adaptive-skills-{uuid4()}",
        )
        session.add(run)
        await session.flush()
        run_id = run.id

    snapshot = await factory.snapshot_for_run(tenant_id=tenant.id, run_id=run_id, role_key="writer")

    plan = snapshot.values["skill_plan"]
    assert snapshot.values["creative_profile"]["themes"] == ["人机情感", "硅基生命"]
    selected = [selection["key"] for selection in plan["selections"]]
    assert selected[:2] == ["novel-write", "project-diagnose"]
    assert {
        "novel-platform-fanqie",
        "novel-speculative-intimacy-writer",
        "novel-serial-quality-review",
    } <= set(selected)
    assert all(selection["layer"] == "style_pack" for selection in plan["selections"][2:])
    intimacy = next(
        selection
        for selection in plan["selections"]
        if selection["key"] == "novel-speculative-intimacy-writer"
    )
    assert any("主题匹配" in reason for reason in intimacy["reasons"])


@pytest.mark.asyncio
async def test_snapshot_includes_only_latest_approved_source_profile(
    factory_data: tuple[AgentFactory, Database, TenantModel, AgentTemplateVersionModel],
) -> None:
    factory, database, tenant, _ = factory_data
    async with database.session() as session:
        project = ProjectModel(tenant_id=tenant.id, name="Moonbound", medium="novel")
        session.add(project)
        await session.flush()
        distillation = SourceDistillationModel(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key="source-v1",
            source_file_ids=["source-1"],
            status="ready",
            pass_key="human_decision",
        )
        session.add(distillation)
        await session.flush()
        approved = SourceProfileModel(
            tenant_id=tenant.id,
            project_id=project.id,
            distillation_id=distillation.id,
            version=1,
            decision="approved",
            profile={"relationship_engine": "rejection-as-protection"},
            evidence_ids=["evidence-1"],
            conflicts=[],
            exclusions=["author imitation"],
        )
        unapproved = SourceProfileModel(
            tenant_id=tenant.id,
            project_id=project.id,
            distillation_id=distillation.id,
            version=2,
            decision="candidate",
            profile={"unsafe": "must not enter context"},
            evidence_ids=["evidence-2"],
            conflicts=[],
            exclusions=[],
        )
        session.add_all([approved, unapproved])
        run = ProjectRunModel(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key=f"approved-profile-{uuid4()}",
        )
        session.add(run)
        await session.flush()
        run_id = run.id

    snapshot = await factory.snapshot_for_run(tenant_id=tenant.id, run_id=run_id, role_key="writer")

    assert snapshot.values["approved_source_profile"]["id"] == approved.id
    assert snapshot.values["approved_source_profile"]["version"] == 1
    assert "unsafe" not in snapshot.values["approved_source_profile"]["profile"]
