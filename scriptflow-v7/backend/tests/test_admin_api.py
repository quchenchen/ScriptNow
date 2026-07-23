from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from scriptflow_v7.app import create_app
from scriptflow_v7.platform.agent_factory import AgentFactory
from scriptflow_v7.platform.auth import AuthService
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.memory import MemoryService
from scriptflow_v7.platform.models import (
    AgentTemplateVersionModel,
    AuditLogModel,
    CreditLedgerModel,
    LanguageModelModel,
    OrderModel,
    ProjectModel,
    ProjectRunModel,
    ProviderModel,
    TenantModel,
    TierModel,
    TokenAccountModel,
    TokenUsageModel,
    UsageReservationModel,
    UserModel,
)


@pytest.fixture
async def admin_api(tmp_path):
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    settings = Settings(
        access_token_secret="test-secret-that-is-at-least-24-bytes",
        agent_studio_url="http://studio.test",
        workspace_root=str(tmp_path / "workspaces"),
    )
    auth = AuthService(database, settings)
    admin_tenant, admin_user = await auth.create_tenant_owner(
        tenant_name="Platform Ops",
        email="admin@example.com",
        password="correct horse battery staple",
    )
    member_tenant, _ = await auth.create_tenant_owner(
        tenant_name="Moon Studio",
        email="member@example.com",
        password="correct horse battery staple",
    )
    async with database.session() as session:
        persisted_admin = await session.get(UserModel, admin_user.id)
        assert persisted_admin is not None
        persisted_admin.is_admin = True
        session.add(TierModel(code="plus", name="Plus", rank=10, monthly_token_quota=10_000))
        session.add_all(
            [
                TokenAccountModel(
                    tenant_id=admin_tenant.id,
                    tier="plus",
                    period_key="2026-07",
                    monthly_available=9_000,
                    credits_available=20,
                ),
                TokenAccountModel(
                    tenant_id=member_tenant.id,
                    tier="plus",
                    period_key="2026-07",
                    monthly_available=0,
                    credits_available=0,
                ),
            ]
        )
    app = create_app(database=database, settings=settings)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as admin,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member,
    ):
        yield admin, member, database, member_tenant.id
    await database.dispose()


async def login(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_overview_and_tenant_search_require_admin_role(admin_api) -> None:
    admin, member, _, _ = admin_api
    await login(admin, "admin@example.com")
    await login(member, "member@example.com")

    assert (await member.get("/admin/api/overview")).status_code == 403
    overview = await admin.get("/admin/api/overview")
    assert overview.json() == {
        "total_tenants": 2,
        "active_tenants": 2,
        "exhausted_tenants": 1,
        "total_tokens": 0,
    }
    page = await admin.get("/admin/api/tenants", params={"search": "member@", "limit": 1})
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0] == {
        "id": page.json()["items"][0]["id"],
        "name": "Moon Studio",
        "owner_email": "member@example.com",
        "tier": "plus",
        "tier_name": "Plus",
        "status": "active",
        "monthly_used": 10_000,
        "monthly_quota": 10_000,
        "credits_available": 0,
        "created_at": page.json()["items"][0]["created_at"],
    }


@pytest.mark.asyncio
async def test_admin_grant_is_idempotent_and_suspension_blocks_existing_sessions(admin_api) -> None:
    admin, member, database, member_tenant_id = admin_api
    await login(admin, "admin@example.com")
    await login(member, "member@example.com")
    csrf = admin.cookies["sf_csrf"]
    body = {
        "tier": "plus",
        "tokens": 2_500,
        "note": "恢复验收额度",
        "idempotency_key": "grant-member-once",
    }
    first = await admin.post(
        f"/admin/api/tenants/{member_tenant_id}/grants",
        headers={"X-CSRF-Token": csrf},
        json=body,
    )
    replay = await admin.post(
        f"/admin/api/tenants/{member_tenant_id}/grants",
        headers={"X-CSRF-Token": csrf},
        json=body,
    )
    assert first.status_code == replay.status_code == 200
    assert first.json()["credits_available"] == replay.json()["credits_available"] == 2_500
    assert replay.json()["idempotent"] is True
    mismatch = await admin.post(
        f"/admin/api/tenants/{member_tenant_id}/grants",
        headers={"X-CSRF-Token": csrf},
        json={**body, "tokens": 9_999},
    )
    assert mismatch.status_code == 409

    suspended = await admin.patch(
        f"/admin/api/tenants/{member_tenant_id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "suspended"},
    )
    assert suspended.status_code == 204
    assert (await member.get("/auth/me")).status_code == 401
    async with database.session() as session:
        account = (
            await session.scalars(
                select(TokenAccountModel).where(TokenAccountModel.tenant_id == member_tenant_id)
            )
        ).one()
        orders = (await session.scalars(select(OrderModel))).all()
        ledger = (
            await session.scalars(
                select(CreditLedgerModel).where(CreditLedgerModel.operation == "grant")
            )
        ).all()
        audits = (
            await session.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.action.in_(["tenant.credits.grant", "tenant.status.change"])
                )
            )
        ).all()
        tenant = await session.get(TenantModel, member_tenant_id)
    assert account.credits_available == 2_500
    assert len(orders) == len(ledger) == 1
    assert len(audits) == 2
    assert tenant is not None and tenant.status == "suspended"


@pytest.mark.asyncio
async def test_admin_can_create_tenant_and_change_tier_with_audit(admin_api) -> None:
    admin, _, database, _ = admin_api
    await login(admin, "admin@example.com")
    csrf = admin.cookies["sf_csrf"]

    async with database.session() as session:
        session.add(TierModel(code="pro", name="Pro", rank=20, monthly_token_quota=50_000))

    tiers = await admin.get("/admin/api/tiers")
    assert tiers.status_code == 200
    assert [item["code"] for item in tiers.json()] == ["plus", "pro"]

    created = await admin.post(
        "/admin/api/tenants",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "New Story Lab",
            "owner_email": "owner@new-story.example",
            "temporary_password": "temporary-password-2026",
            "tier": "plus",
        },
    )
    assert created.status_code == 201
    tenant_id = created.json()["id"]
    assert created.json()["monthly_quota"] == 10_000

    changed = await admin.patch(
        f"/admin/api/tenants/{tenant_id}/tier",
        headers={"X-CSRF-Token": csrf},
        json={"tier": "pro", "note": "运营升级"},
    )
    assert changed.status_code == 200
    assert changed.json()["tier"] == "pro"
    assert changed.json()["monthly_quota"] == 50_000

    duplicate = await admin.post(
        "/admin/api/tenants",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Duplicate",
            "owner_email": "owner@new-story.example",
            "temporary_password": "temporary-password-2026",
            "tier": "plus",
        },
    )
    assert duplicate.status_code == 409

    async with database.session() as session:
        tenant = await session.get(TenantModel, tenant_id)
        owner = (
            await session.scalars(select(UserModel).where(UserModel.tenant_id == tenant_id))
        ).one()
        accounts = (
            await session.scalars(
                select(TokenAccountModel).where(TokenAccountModel.tenant_id == tenant_id)
            )
        ).all()
        audits = (
            await session.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.resource_id == tenant_id,
                    AuditLogModel.action.in_(["tenant.create", "tenant.tier.change"]),
                )
            )
        ).all()
    assert tenant is not None and tenant.tier == "pro"
    assert owner.email == "owner@new-story.example"
    assert {(item.tier, item.monthly_available) for item in accounts} == {
        ("plus", 10_000),
        ("pro", 50_000),
    }
    assert len(audits) == 2


@pytest.mark.asyncio
async def test_admin_usage_aggregates_price_snapshots_and_trace_links(admin_api) -> None:
    admin, member, database, member_tenant_id = admin_api
    await login(admin, "admin@example.com")
    await login(member, "member@example.com")

    async with database.session() as session:
        project = ProjectModel(
            tenant_id=member_tenant_id,
            name="Measured Story",
            medium="script",
            source_mode="original",
        )
        session.add(project)
        await session.flush()
        run = ProjectRunModel(
            tenant_id=member_tenant_id,
            project_id=project.id,
            idempotency_key="admin-usage-test",
            status="succeeded",
        )
        session.add(run)
        await session.flush()
        reservation = UsageReservationModel(
            tenant_id=member_tenant_id,
            run_id=run.id,
            idempotency_key="admin-usage-reservation",
            tier="plus",
            period_key="2026-07",
            monthly_reserved=500,
            credits_reserved=0,
            actual_tokens=300,
            status="finalized",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            finalized_at=datetime.now(UTC),
        )
        session.add(reservation)
        await session.flush()
        session.add_all(
            [
                TokenUsageModel(
                    reservation_id=reservation.id,
                    tenant_id=member_tenant_id,
                    project_id=project.id,
                    run_id=run.id,
                    framework_event_id="model-call-1",
                    trace_id="trace-admin-usage",
                    agent_role="writer",
                    model_key="qwen-test",
                    input_tokens=100,
                    output_tokens=50,
                    input_price_per_million=Decimal("2.0"),
                    output_price_per_million=Decimal("8.0"),
                    cost_estimate=Decimal("0.0006"),
                ),
                TokenUsageModel(
                    reservation_id=reservation.id,
                    tenant_id=member_tenant_id,
                    project_id=project.id,
                    run_id=run.id,
                    framework_event_id="model-call-2",
                    trace_id="trace-admin-usage",
                    agent_role="writer",
                    model_key="qwen-test",
                    input_tokens=80,
                    output_tokens=70,
                    input_price_per_million=Decimal("2.0"),
                    output_price_per_million=Decimal("8.0"),
                    cost_estimate=Decimal("0.00072"),
                ),
            ]
        )

    assert (await member.get("/admin/api/usage/runs")).status_code == 403
    response = await admin.get("/admin/api/usage/runs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "input_tokens": 180,
        "output_tokens": 120,
        "total_tokens": 300,
        "estimated_cost": 0.00132,
        "currency": "CNY",
    }
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["tenant_name"] == "Moon Studio"
    assert item["project_name"] == "Measured Story"
    assert item["trace_id"] == "trace-admin-usage"
    assert item["trace_url"] == "http://studio.test/traces/trace-admin-usage"
    assert item["input_price_per_million"] == 2.0
    assert item["output_price_per_million"] == 8.0
    assert item["is_mock"] is False


@pytest.mark.asyncio
async def test_admin_supply_changes_creator_model_visibility_without_secret_echo(admin_api) -> None:
    admin, member, database, member_tenant_id = admin_api
    await login(admin, "admin@example.com")
    await login(member, "member@example.com")
    csrf = admin.cookies["sf_csrf"]

    async with database.session() as session:
        session.add(TierModel(code="pro", name="Pro", rank=20, monthly_token_quota=50_000))
        project = ProjectModel(
            tenant_id=member_tenant_id,
            name="Supply Visibility",
            medium="script",
            source_mode="original",
        )
        session.add(project)
        await session.flush()
        project_id = project.id

    provider = await admin.post(
        "/admin/api/providers",
        headers={"X-CSRF-Token": csrf},
        json={
            "key": "openai-qa",
            "name": "OpenAI QA",
            "base_url": "https://api.example.invalid/v1",
            "credential": "sk-provider-secret-never-return",
        },
    )
    assert provider.status_code == 200
    assert provider.json()["credential_configured"] is True
    assert "sk-provider-secret-never-return" not in provider.text
    assert set(provider.json()) == {
        "id",
        "key",
        "name",
        "base_url",
        "status",
        "credential_configured",
    }
    provider_id = provider.json()["id"]

    model = await admin.post(
        "/admin/api/models",
        headers={"X-CSRF-Token": csrf},
        json={
            "key": "gpt-qa",
            "display_name": "GPT QA",
            "provider_id": provider_id,
            "agentscope_class": "OpenAIChatModel",
            "min_tier_code": "pro",
            "input_price_per_million": 2.5,
            "output_price_per_million": 10,
            "enabled": True,
        },
    )
    assert model.status_code == 200

    locked = await member.get(f"/projects/{project_id}/models")
    locked_item = next(item for item in locked.json() if item["key"] == "gpt-qa")
    assert locked_item["available"] is False
    assert locked_item["reason"] == "upgrade_required"

    changed = await admin.patch(
        f"/admin/api/tenants/{member_tenant_id}/tier",
        headers={"X-CSRF-Token": csrf},
        json={"tier": "pro", "note": "供给可见性验收"},
    )
    assert changed.status_code == 200
    visible = await member.get(f"/projects/{project_id}/models")
    visible_item = next(item for item in visible.json() if item["key"] == "gpt-qa")
    assert visible_item["available"] is True
    assert visible_item["reason"] is None

    tier_updated = await admin.put(
        "/admin/api/tiers/pro",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Pro",
            "rank": 20,
            "monthly_price": 199,
            "monthly_token_quota": 80_000,
            "enabled": True,
        },
    )
    assert tier_updated.status_code == 200
    assert tier_updated.json()["monthly_token_quota"] == 80_000

    supply = await admin.get("/admin/api/supply")
    assert supply.status_code == 200
    assert supply.json()["providers"][0]["credential_configured"] is True
    assert "sk-provider-secret-never-return" not in supply.text
    async with database.session() as session:
        actions = set(
            (
                await session.scalars(
                    select(AuditLogModel.action).where(
                        AuditLogModel.action.in_(
                            ["provider.configure", "model.configure", "tier.configure"]
                        )
                    )
                )
            ).all()
        )
    assert actions == {"provider.configure", "model.configure", "tier.configure"}


@pytest.mark.asyncio
async def test_provider_delete_blocks_referenced_models_then_cascades_unreferenced_models(
    admin_api,
) -> None:
    admin, _, database, _ = admin_api
    await login(admin, "admin@example.com")
    csrf = admin.cookies["sf_csrf"]
    provider = (
        await admin.post(
            "/admin/api/providers",
            headers={"X-CSRF-Token": csrf},
            json={
                "key": "delete-test",
                "name": "Delete Test",
                "base_url": "https://example.invalid/v1",
                "credential": "secret",
            },
        )
    ).json()
    model = (
        await admin.post(
            "/admin/api/models",
            headers={"X-CSRF-Token": csrf},
            json={
                "key": "delete-model",
                "display_name": "Delete Model",
                "provider_id": provider["id"],
                "agentscope_class": "OpenAIChatModel",
                "min_tier_code": "plus",
                "input_price_per_million": 0,
                "output_price_per_million": 0,
                "enabled": False,
            },
        )
    ).json()
    async with database.session() as session:
        template = AgentTemplateVersionModel(
            role_key="delete-test", version=1, soul="test", default_model_id=model["id"]
        )
        session.add(template)
        await session.flush()
        template_id = template.id

    blocked = await admin.delete(
        f"/admin/api/providers/{provider['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert blocked.status_code == 409
    assert "Agent 模板" in blocked.json()["detail"]

    async with database.session() as session:
        template = await session.get(AgentTemplateVersionModel, template_id)
        await session.delete(template)
    deleted = await admin.delete(
        f"/admin/api/providers/{provider['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert deleted.status_code == 204
    async with database.session() as session:
        assert await session.get(ProviderModel, provider["id"]) is None
        assert await session.get(LanguageModelModel, model["id"]) is None


@pytest.mark.asyncio
async def test_template_and_tool_mount_change_only_the_next_run(admin_api) -> None:
    admin, _, database, tenant_id = admin_api
    await login(admin, "admin@example.com")
    csrf = admin.cookies["sf_csrf"]
    async with database.session() as session:
        tier = (await session.scalars(select(TierModel).where(TierModel.code == "plus"))).one()
        provider = ProviderModel(key="cap-test", name="Capability", status="connected")
        session.add(provider)
        await session.flush()
        model = LanguageModelModel(
            key="cap-model",
            display_name="Capability",
            provider_id=provider.id,
            agentscope_class="OpenAIChatModel",
            min_tier_id=tier.id,
        )
        project = ProjectModel(
            tenant_id=tenant_id, name="Capability", medium="script", source_mode="original"
        )
        session.add_all([model, project])
        await session.flush()
        model_id, project_id = model.id, project.id
    draft = await admin.post(
        "/admin/api/agent-templates",
        headers={"X-CSRF-Token": csrf},
        json={"role_key": "writer", "soul": "Draft soul", "default_model_id": model_id},
    )
    assert draft.status_code == 200 and draft.json()["published"] is False
    assert (
        await admin.post(
            f"/admin/api/agent-templates/{draft.json()['id']}/publish",
            headers={"X-CSRF-Token": csrf},
        )
    ).status_code == 200
    group = await admin.post(
        "/admin/api/tool-groups",
        headers={"X-CSRF-Token": csrf},
        json={
            "key": "script.read",
            "name": "Script Read",
            "tool_keys": ["script.read.story_map"],
            "min_tier_code": "plus",
            "enabled": True,
        },
    )
    assert group.status_code == 200
    mount_body = {"role_key": "writer", "tool_group_id": group.json()["id"], "enabled": True}
    assert (
        await admin.put("/admin/api/tool-mounts", headers={"X-CSRF-Token": csrf}, json=mount_body)
    ).status_code == 200
    async with database.session() as session:
        run = ProjectRunModel(tenant_id=tenant_id, project_id=project_id, idempotency_key="cap-1")
        session.add(run)
        await session.flush()
        run_id = run.id
    factory = AgentFactory(database)
    first = await factory.snapshot_for_run(tenant_id=tenant_id, run_id=run_id, role_key="writer")
    assert first.values["tool_keys"] == ["script.read.story_map"]
    assert (
        await admin.put(
            "/admin/api/tool-mounts",
            headers={"X-CSRF-Token": csrf},
            json={**mount_body, "enabled": False},
        )
    ).status_code == 200
    assert (
        await factory.snapshot_for_run(tenant_id=tenant_id, run_id=run_id, role_key="writer")
    ).fingerprint == first.fingerprint
    async with database.session() as session:
        next_run = ProjectRunModel(
            tenant_id=tenant_id, project_id=project_id, idempotency_key="cap-2"
        )
        session.add(next_run)
        await session.flush()
        next_run_id = next_run.id
    second = await factory.snapshot_for_run(
        tenant_id=tenant_id, run_id=next_run_id, role_key="writer"
    )
    assert second.values["tool_keys"] == []


@pytest.mark.asyncio
async def test_memory_governance_uses_shared_service_and_append_only_audit(
    admin_api, tmp_path
) -> None:
    admin, _, database, tenant_id = admin_api
    await login(admin, "admin@example.com")
    csrf = admin.cookies["sf_csrf"]
    async with database.session() as session:
        project = ProjectModel(
            tenant_id=tenant_id, name="Memory QA", medium="novel", source_mode="original"
        )
        session.add(project)
        await session.flush()
        project_id = project.id
    service = MemoryService(database, tmp_path / "workspaces")
    entry_id = await service.add(
        tenant_id=tenant_id,
        project_id=project_id,
        role_key="writer",
        actor_id="agent",
        content="Keep the original decision",
    )
    listed = await admin.get("/admin/api/memories")
    assert (
        listed.status_code == 200
        and listed.json()["items"][0]["content"] == "Keep the original decision"
    )
    corrected = await admin.put(
        f"/admin/api/memories/{entry_id}?tenant_id={tenant_id}&project_id={project_id}",
        headers={"X-CSRF-Token": csrf},
        json={"content": "Corrected decision"},
    )
    compressed = await admin.post(
        f"/admin/api/memories/{entry_id}/compress?tenant_id={tenant_id}&project_id={project_id}",
        headers={"X-CSRF-Token": csrf},
        json={"content": "Decision summary"},
    )
    assert corrected.status_code == compressed.status_code == 204
    rejected = await admin.put(
        "/admin/api/memory-policies/writer",
        headers={"X-CSRF-Token": csrf},
        json={
            "memory_max_tokens": 4000,
            "trigger_ratio": 0.7,
            "reserve_ratio": 0.2,
            "memory_instructions": "Preserve decisions",
            "preserve_creative_decisions": False,
        },
    )
    assert rejected.status_code == 422
    policy = await admin.put(
        "/admin/api/memory-policies/writer",
        headers={"X-CSRF-Token": csrf},
        json={
            "memory_max_tokens": 4000,
            "trigger_ratio": 0.7,
            "reserve_ratio": 0.2,
            "memory_instructions": "Preserve decisions",
            "preserve_creative_decisions": True,
        },
    )
    assert policy.status_code == 200
    deleted = await admin.delete(
        f"/admin/api/memories/{entry_id}?tenant_id={tenant_id}&project_id={project_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204
    final = await admin.get("/admin/api/memories")
    assert final.json()["items"] == []
    assert {item["operation"] for item in final.json()["audit"]} == {
        "create",
        "correct",
        "compress",
        "delete",
    }
