import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from scriptnow.platform.billing import BillingError, BillingService, PaymentRequired
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreditLedgerModel,
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    ReservationState,
    TenantModel,
    TokenAccountModel,
    TokenUsageModel,
)


@pytest.fixture
async def billing_data(tmp_path) -> tuple[BillingService, Database, TenantModel, ProjectRunModel]:
    database = Database.create(f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio", tier="pro")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Story", medium=ProjectMedium.SCRIPT)
        session.add(project)
        await session.flush()
        run = ProjectRunModel(tenant_id=tenant.id, project_id=project.id, idempotency_key="run")
        account = TokenAccountModel(
            tenant_id=tenant.id,
            tier="pro",
            period_key="2026-07",
            monthly_available=100,
            credits_available=50,
        )
        session.add_all([run, account])
        await session.flush()
    yield BillingService(database), database, tenant, run
    await database.dispose()


@pytest.mark.asyncio
async def test_concurrent_reserve_cannot_double_spend(
    billing_data: tuple[BillingService, Database, TenantModel, ProjectRunModel],
) -> None:
    billing, database, tenant, run = billing_data
    results = await asyncio.gather(
        billing.reserve(
            tenant_id=tenant.id, run_id=run.id, idempotency_key="one", tier="pro", max_tokens=100
        ),
        billing.reserve(
            tenant_id=tenant.id, run_id=run.id, idempotency_key="two", tier="pro", max_tokens=100
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, PaymentRequired) for result in results) == 1
    async with database.session() as session:
        account = (await session.scalars(select(TokenAccountModel))).one()
        assert account.monthly_available + account.credits_available == 50


@pytest.mark.asyncio
async def test_usage_dedupe_fallback_cost_snapshot_and_finalize(
    billing_data: tuple[BillingService, Database, TenantModel, ProjectRunModel],
) -> None:
    billing, database, tenant, run = billing_data
    reservation = await billing.reserve(
        tenant_id=tenant.id, run_id=run.id, idempotency_key="generation", tier="pro", max_tokens=120
    )
    common = {
        "reservation_id": reservation.id,
        "tenant_id": tenant.id,
        "run_id": run.id,
        "trace_id": "trace-1",
        "agent_role": "writer",
        "input_price_per_million": Decimal("10"),
        "output_price_per_million": Decimal("20"),
    }
    first_id = await billing.record_model_call(
        **common,
        framework_event_id="primary-failed",
        model_key="primary",
        input_tokens=10,
        output_tokens=0,
    )
    assert (
        await billing.record_model_call(
            **common,
            framework_event_id="primary-failed",
            model_key="primary",
            input_tokens=999,
            output_tokens=999,
        )
        == first_id
    )
    await billing.record_model_call(
        **common,
        framework_event_id="fallback-success",
        model_key="fallback",
        input_tokens=30,
        output_tokens=40,
    )
    finalized = await billing.finalize(reservation.id)
    replay = await billing.finalize(reservation.id)

    assert finalized == replay
    assert finalized.actual_tokens == 80
    assert finalized.status == ReservationState.FINALIZED
    async with database.session() as session:
        usage = (
            await session.scalars(select(TokenUsageModel).order_by(TokenUsageModel.created_at))
        ).all()
        ledger = (
            await session.scalars(select(CreditLedgerModel).order_by(CreditLedgerModel.created_at))
        ).all()
        account = (await session.scalars(select(TokenAccountModel))).one()
        assert len(usage) == 2
        assert [entry.operation for entry in ledger] == ["reserve", "finalize"]
        assert (account.monthly_available, account.credits_available) == (20, 50)
        assert str(usage[1].cost_estimate) == "0.001100"


@pytest.mark.asyncio
async def test_release_reverse_and_append_only_audit(
    billing_data: tuple[BillingService, Database, TenantModel, ProjectRunModel],
) -> None:
    billing, database, tenant, run = billing_data
    released = await billing.reserve(
        tenant_id=tenant.id, run_id=run.id, idempotency_key="release", tier="pro", max_tokens=30
    )
    await billing.release(released.id)
    await billing.release(released.id)
    finalized = await billing.reserve(
        tenant_id=tenant.id, run_id=run.id, idempotency_key="reverse", tier="pro", max_tokens=40
    )
    await billing.record_model_call(
        reservation_id=finalized.id,
        tenant_id=tenant.id,
        run_id=run.id,
        framework_event_id="call",
        trace_id="trace",
        agent_role="writer",
        model_key="model",
        input_tokens=10,
        output_tokens=20,
        input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("1"),
    )
    await billing.finalize(finalized.id)
    await billing.reverse(finalized.id)
    await billing.reverse(finalized.id)

    async with database.session() as session:
        account = (await session.scalars(select(TokenAccountModel))).one()
        entries = (
            await session.scalars(select(CreditLedgerModel).order_by(CreditLedgerModel.created_at))
        ).all()
        assert (account.monthly_available, account.credits_available) == (100, 50)
        assert [entry.operation for entry in entries] == [
            "reserve",
            "release",
            "reserve",
            "finalize",
            "reverse",
        ]
        assert entries[-1].reversal_of_id == entries[-2].id
        entries[0].monthly_delta = 999
        with pytest.raises(ValueError, match="append-only"):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_usage_cannot_exceed_reservation(
    billing_data: tuple[BillingService, Database, TenantModel, ProjectRunModel],
) -> None:
    billing, _, tenant, run = billing_data
    reservation = await billing.reserve(
        tenant_id=tenant.id, run_id=run.id, idempotency_key="small", tier="pro", max_tokens=10
    )
    await billing.record_model_call(
        reservation_id=reservation.id,
        tenant_id=tenant.id,
        run_id=run.id,
        framework_event_id="overspend",
        trace_id="trace",
        agent_role="writer",
        model_key="model",
        input_tokens=11,
        output_tokens=0,
        input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("1"),
    )
    with pytest.raises(BillingError, match="exceeded"):
        await billing.finalize(reservation.id)


@pytest.mark.asyncio
async def test_development_billing_records_overspend_without_blocking(
    billing_data: tuple[BillingService, Database, TenantModel, ProjectRunModel],
) -> None:
    _, database, tenant, run = billing_data
    billing = BillingService(database, enforce_limits=False)
    reservation = await billing.reserve(
        tenant_id=tenant.id,
        run_id=run.id,
        idempotency_key="development-overspend",
        tier="pro",
        max_tokens=10,
    )
    await billing.record_model_call(
        reservation_id=reservation.id,
        tenant_id=tenant.id,
        run_id=run.id,
        framework_event_id="development-call",
        trace_id="trace",
        agent_role="writer",
        model_key="model",
        input_tokens=21,
        output_tokens=0,
        input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("1"),
    )

    finalized = await billing.finalize(reservation.id)

    assert finalized.actual_tokens == 21
    assert finalized.status == ReservationState.FINALIZED
