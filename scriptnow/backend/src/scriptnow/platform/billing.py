from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text

from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreditLedgerModel,
    ProjectRunModel,
    ReservationState,
    TokenAccountModel,
    TokenUsageModel,
    UsageReservationModel,
)


class BillingError(RuntimeError):
    pass


class PaymentRequired(BillingError):
    pass


@dataclass(frozen=True, slots=True)
class ReservationView:
    id: str
    status: str
    monthly_reserved: int
    credits_reserved: int
    actual_tokens: int | None

    @property
    def reserved_tokens(self) -> int:
        return self.monthly_reserved + self.credits_reserved


class BillingService:
    def __init__(self, database: Database, *, enforce_limits: bool = True) -> None:
        self.database = database
        self.enforce_limits = enforce_limits

    async def reserve(
        self,
        *,
        tenant_id: str,
        run_id: str,
        idempotency_key: str,
        tier: str,
        max_tokens: int,
        ttl_minutes: int = 30,
    ) -> ReservationView:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        async with self.database.session() as session:
            await self._write_lock(session)
            existing = (
                await session.scalars(
                    select(UsageReservationModel).where(
                        UsageReservationModel.tenant_id == tenant_id,
                        UsageReservationModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                if existing.run_id != run_id or existing.tier != tier:
                    raise BillingError("idempotency key was reused with different scope")
                return self._view(existing)
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise BillingError("run is outside tenant scope")
            account = await self._account(session, tenant_id, tier)
            if (
                self.enforce_limits
                and account.monthly_available + account.credits_available < max_tokens
            ):
                raise PaymentRequired("insufficient token balance")
            monthly_before = account.monthly_available
            credits_before = account.credits_available
            monthly = min(monthly_before, max_tokens)
            credits = max_tokens - monthly
            account.monthly_available -= monthly
            account.credits_available -= credits
            account.row_version += 1
            reservation = UsageReservationModel(
                tenant_id=tenant_id,
                run_id=run_id,
                idempotency_key=idempotency_key,
                tier=tier,
                period_key=account.period_key,
                monthly_reserved=monthly,
                credits_reserved=credits,
                expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
            )
            session.add(reservation)
            await session.flush()
            self._entry(
                session,
                account,
                reservation,
                operation="reserve",
                monthly_delta=-monthly,
                credits_delta=-credits,
                monthly_before=monthly_before,
                credits_before=credits_before,
            )
            return self._view(reservation)

    async def record_model_call(
        self,
        *,
        reservation_id: str,
        tenant_id: str,
        run_id: str,
        framework_event_id: str,
        trace_id: str,
        agent_role: str,
        model_key: str,
        input_tokens: int,
        output_tokens: int,
        input_price_per_million: Decimal,
        output_price_per_million: Decimal,
        currency: str = "CNY",
    ) -> str:
        if input_tokens < 0 or output_tokens < 0:
            raise BillingError("token usage cannot be negative")
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise BillingError("run is outside tenant scope")
            reservation = await session.get(UsageReservationModel, reservation_id)
            if (
                reservation is None
                or reservation.tenant_id != tenant_id
                or reservation.run_id != run_id
                or reservation.status != ReservationState.RESERVED
            ):
                raise BillingError("usage is outside an active reservation")
            existing = (
                await session.scalars(
                    select(TokenUsageModel).where(
                        TokenUsageModel.run_id == run_id,
                        TokenUsageModel.framework_event_id == framework_event_id,
                    )
                )
            ).one_or_none()
            if existing:
                return existing.id
            cost = (
                Decimal(input_tokens) * input_price_per_million
                + Decimal(output_tokens) * output_price_per_million
            ) / Decimal(1_000_000)
            usage = TokenUsageModel(
                reservation_id=reservation_id,
                tenant_id=tenant_id,
                project_id=run.project_id,
                run_id=run_id,
                framework_event_id=framework_event_id,
                trace_id=trace_id,
                agent_role=agent_role,
                model_key=model_key,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
                cost_estimate=cost,
                currency=currency,
            )
            session.add(usage)
            await session.flush()
            return usage.id

    async def finalize(self, reservation_id: str) -> ReservationView:
        async with self.database.session() as session:
            await self._write_lock(session)
            reservation = await session.get(UsageReservationModel, reservation_id)
            if reservation is None:
                raise BillingError("reservation does not exist")
            actual = int(
                await session.scalar(
                    select(
                        func.coalesce(
                            func.sum(TokenUsageModel.input_tokens + TokenUsageModel.output_tokens),
                            0,
                        )
                    ).where(TokenUsageModel.reservation_id == reservation.id)
                )
                or 0
            )
            if reservation.status == ReservationState.FINALIZED:
                if reservation.actual_tokens != actual:
                    raise BillingError("usage changed after finalization")
                return self._view(reservation)
            if reservation.status != ReservationState.RESERVED:
                raise BillingError(f"cannot finalize {reservation.status}")
            if (
                self.enforce_limits
                and actual > reservation.monthly_reserved + reservation.credits_reserved
            ):
                raise BillingError("actual usage exceeded reservation")
            account = await self._account(session, reservation.tenant_id, reservation.tier)
            monthly_used = min(actual, reservation.monthly_reserved)
            credits_used = actual - monthly_used
            monthly_refund = reservation.monthly_reserved - monthly_used
            credits_refund = reservation.credits_reserved - credits_used
            before_monthly = account.monthly_available
            before_credits = account.credits_available
            account.monthly_available += monthly_refund
            account.credits_available += credits_refund
            account.row_version += 1
            reservation.actual_tokens = actual
            reservation.status = ReservationState.FINALIZED
            reservation.finalized_at = datetime.now(UTC)
            self._entry(
                session,
                account,
                reservation,
                operation="finalize",
                monthly_delta=monthly_refund,
                credits_delta=credits_refund,
                monthly_before=before_monthly,
                credits_before=before_credits,
                actual_tokens=actual,
            )
            return self._view(reservation)

    async def release(self, reservation_id: str, *, expired: bool = False) -> ReservationView:
        operation = "expire" if expired else "release"
        async with self.database.session() as session:
            await self._write_lock(session)
            reservation = await session.get(UsageReservationModel, reservation_id)
            if reservation is None:
                raise BillingError("reservation does not exist")
            if reservation.status == ReservationState.RELEASED:
                return self._view(reservation)
            if reservation.status != ReservationState.RESERVED:
                raise BillingError(f"cannot release {reservation.status}")
            account = await self._account(session, reservation.tenant_id, reservation.tier)
            before_monthly = account.monthly_available
            before_credits = account.credits_available
            account.monthly_available += reservation.monthly_reserved
            account.credits_available += reservation.credits_reserved
            account.row_version += 1
            reservation.status = ReservationState.RELEASED
            self._entry(
                session,
                account,
                reservation,
                operation=operation,
                monthly_delta=reservation.monthly_reserved,
                credits_delta=reservation.credits_reserved,
                monthly_before=before_monthly,
                credits_before=before_credits,
            )
            return self._view(reservation)

    async def reverse(self, reservation_id: str) -> ReservationView:
        async with self.database.session() as session:
            await self._write_lock(session)
            reservation = await session.get(UsageReservationModel, reservation_id)
            if reservation is None:
                raise BillingError("reservation does not exist")
            if reservation.status == ReservationState.REVERSED:
                return self._view(reservation)
            if reservation.status != ReservationState.FINALIZED:
                raise BillingError(f"cannot reverse {reservation.status}")
            account = await self._account(session, reservation.tenant_id, reservation.tier)
            actual = reservation.actual_tokens or 0
            monthly = min(actual, reservation.monthly_reserved)
            credits = actual - monthly
            before_monthly = account.monthly_available
            before_credits = account.credits_available
            account.monthly_available += monthly
            account.credits_available += credits
            account.row_version += 1
            reservation.status = ReservationState.REVERSED
            finalized = (
                await session.scalars(
                    select(CreditLedgerModel).where(
                        CreditLedgerModel.reservation_id == reservation.id,
                        CreditLedgerModel.operation == "finalize",
                    )
                )
            ).one()
            self._entry(
                session,
                account,
                reservation,
                operation="reverse",
                monthly_delta=monthly,
                credits_delta=credits,
                monthly_before=before_monthly,
                credits_before=before_credits,
                actual_tokens=actual,
                reversal_of_id=finalized.id,
            )
            return self._view(reservation)

    @staticmethod
    async def _write_lock(session: object) -> None:
        bind = session.get_bind()  # type: ignore[attr-defined]
        if bind.dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))  # type: ignore[attr-defined]

    @staticmethod
    async def _account(session: object, tenant_id: str, tier: str) -> TokenAccountModel:
        account = (
            await session.scalars(  # type: ignore[attr-defined]
                select(TokenAccountModel).where(
                    TokenAccountModel.tenant_id == tenant_id,
                    TokenAccountModel.tier == tier,
                )
            )
        ).one_or_none()
        if account is None:
            raise PaymentRequired("no balance for tenant tier")
        return account

    @staticmethod
    def _entry(
        session: object,
        account: TokenAccountModel,
        reservation: UsageReservationModel,
        *,
        operation: str,
        monthly_delta: int,
        credits_delta: int,
        monthly_before: int,
        credits_before: int,
        actual_tokens: int | None = None,
        reversal_of_id: str | None = None,
    ) -> None:
        session.add(  # type: ignore[attr-defined]
            CreditLedgerModel(
                tenant_id=reservation.tenant_id,
                reservation_id=reservation.id,
                run_id=reservation.run_id,
                operation=operation,
                tier=reservation.tier,
                period_key=reservation.period_key,
                currency=account.currency,
                monthly_delta=monthly_delta,
                credits_delta=credits_delta,
                monthly_before=monthly_before,
                monthly_after=account.monthly_available,
                credits_before=credits_before,
                credits_after=account.credits_available,
                actual_tokens=actual_tokens,
                reversal_of_id=reversal_of_id,
            )
        )

    @staticmethod
    def _view(reservation: UsageReservationModel) -> ReservationView:
        return ReservationView(
            id=reservation.id,
            status=str(reservation.status),
            monthly_reserved=reservation.monthly_reserved,
            credits_reserved=reservation.credits_reserved,
            actual_tokens=reservation.actual_tokens,
        )
