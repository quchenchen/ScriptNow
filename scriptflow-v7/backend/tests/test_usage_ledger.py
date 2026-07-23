import asyncio
from uuid import uuid4

import pytest

from scriptflow_v7.platform.ledger import (
    InMemoryUsageLedger,
    InsufficientBalance,
    InvalidReservation,
    ReservationStatus,
    TokenAccount,
)


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_spend_the_same_balance() -> None:
    tenant_id = uuid4()
    ledger = InMemoryUsageLedger(TokenAccount(tenant_id, "pro", 100, 0))

    results = await asyncio.gather(
        ledger.reserve(
            tenant_id=tenant_id,
            run_id="run-1",
            idempotency_key="request-1",
            tier="pro",
            max_tokens=80,
        ),
        ledger.reserve(
            tenant_id=tenant_id,
            run_id="run-2",
            idempotency_key="request-2",
            tier="pro",
            max_tokens=80,
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, InsufficientBalance) for item in results) == 1
    assert ledger.account.monthly_available == 20


@pytest.mark.asyncio
async def test_reserve_and_finalize_are_idempotent_and_refund_unused_tokens() -> None:
    tenant_id = uuid4()
    ledger = InMemoryUsageLedger(TokenAccount(tenant_id, "pro", 50, 100))
    kwargs = {
        "tenant_id": tenant_id,
        "run_id": "run-1",
        "idempotency_key": "request-1",
        "tier": "pro",
        "max_tokens": 80,
    }

    first = await ledger.reserve(**kwargs)
    duplicate = await ledger.reserve(**kwargs)
    await ledger.finalize(first.id, 60)
    await ledger.finalize(first.id, 60)

    assert duplicate.id == first.id
    assert first.status == ReservationStatus.FINALIZED
    assert (ledger.account.monthly_available, ledger.account.credits_available) == (0, 90)
    assert [entry.operation for entry in ledger.entries] == ["reserve", "finalize"]


@pytest.mark.asyncio
async def test_failed_run_release_and_finalized_reverse_are_replay_safe() -> None:
    tenant_id = uuid4()
    ledger = InMemoryUsageLedger(TokenAccount(tenant_id, "plus", 100, 0))
    released = await ledger.reserve(
        tenant_id=tenant_id,
        run_id="failed",
        idempotency_key="failed-request",
        tier="plus",
        max_tokens=40,
    )
    await ledger.release(released.id)
    await ledger.release(released.id)

    finalized = await ledger.reserve(
        tenant_id=tenant_id,
        run_id="done",
        idempotency_key="done-request",
        tier="plus",
        max_tokens=70,
    )
    await ledger.finalize(finalized.id, 30)
    await ledger.reverse(finalized.id)
    await ledger.reverse(finalized.id)

    assert ledger.account.monthly_available == 100
    assert [entry.operation for entry in ledger.entries] == [
        "reserve",
        "release",
        "reserve",
        "finalize",
        "reverse",
    ]


@pytest.mark.asyncio
async def test_finalize_replay_cannot_change_actual_usage() -> None:
    tenant_id = uuid4()
    ledger = InMemoryUsageLedger(TokenAccount(tenant_id, "max", 100, 0))
    reservation = await ledger.reserve(
        tenant_id=tenant_id,
        run_id="run-1",
        idempotency_key="request-1",
        tier="max",
        max_tokens=50,
    )
    await ledger.finalize(reservation.id, 20)

    with pytest.raises(InvalidReservation, match="changed actual_tokens"):
        await ledger.finalize(reservation.id, 21)
