import asyncio
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4


class InsufficientBalance(RuntimeError):
    pass


class InvalidReservation(RuntimeError):
    pass


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    FINALIZED = "finalized"
    RELEASED = "released"
    REVERSED = "reversed"


@dataclass(slots=True)
class TokenAccount:
    tenant_id: UUID
    tier: str
    monthly_available: int
    credits_available: int


@dataclass(slots=True)
class UsageReservation:
    id: UUID
    tenant_id: UUID
    run_id: str
    idempotency_key: str
    tier: str
    monthly_reserved: int
    credits_reserved: int
    status: ReservationStatus = ReservationStatus.RESERVED
    actual_tokens: int | None = None

    @property
    def reserved_tokens(self) -> int:
        return self.monthly_reserved + self.credits_reserved


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    reservation_id: UUID
    operation: str
    monthly_delta: int
    credits_delta: int
    actual_tokens: int | None = None


class InMemoryUsageLedger:
    """Executable transaction model; P1 persists the same state transitions."""

    def __init__(self, account: TokenAccount) -> None:
        self.account = account
        self.reservations: dict[UUID, UsageReservation] = {}
        self.entries: list[LedgerEntry] = []
        self._idempotency: dict[tuple[UUID, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def reserve(
        self,
        *,
        tenant_id: UUID,
        run_id: str,
        idempotency_key: str,
        tier: str,
        max_tokens: int,
    ) -> UsageReservation:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        async with self._lock:
            if tenant_id != self.account.tenant_id or tier != self.account.tier:
                raise InsufficientBalance("no account for the trusted tenant and tier")
            existing_id = self._idempotency.get((tenant_id, idempotency_key))
            if existing_id is not None:
                return self.reservations[existing_id]
            if self.account.monthly_available + self.account.credits_available < max_tokens:
                raise InsufficientBalance("insufficient token balance")

            monthly = min(self.account.monthly_available, max_tokens)
            credits = max_tokens - monthly
            self.account.monthly_available -= monthly
            self.account.credits_available -= credits
            reservation = UsageReservation(
                id=uuid4(),
                tenant_id=tenant_id,
                run_id=run_id,
                idempotency_key=idempotency_key,
                tier=tier,
                monthly_reserved=monthly,
                credits_reserved=credits,
            )
            self.reservations[reservation.id] = reservation
            self._idempotency[(tenant_id, idempotency_key)] = reservation.id
            self.entries.append(LedgerEntry(reservation.id, "reserve", -monthly, -credits))
            return reservation

    async def finalize(self, reservation_id: UUID, actual_tokens: int) -> UsageReservation:
        async with self._lock:
            reservation = self.reservations[reservation_id]
            if reservation.status == ReservationStatus.FINALIZED:
                if reservation.actual_tokens != actual_tokens:
                    raise InvalidReservation("finalize replay changed actual_tokens")
                return reservation
            if reservation.status != ReservationStatus.RESERVED:
                raise InvalidReservation(f"cannot finalize {reservation.status}")
            if actual_tokens < 0 or actual_tokens > reservation.reserved_tokens:
                raise InvalidReservation("actual_tokens must fit within the reservation")

            monthly_used = min(actual_tokens, reservation.monthly_reserved)
            credits_used = actual_tokens - monthly_used
            monthly_refund = reservation.monthly_reserved - monthly_used
            credits_refund = reservation.credits_reserved - credits_used
            self.account.monthly_available += monthly_refund
            self.account.credits_available += credits_refund
            reservation.actual_tokens = actual_tokens
            reservation.status = ReservationStatus.FINALIZED
            self.entries.append(
                LedgerEntry(
                    reservation.id,
                    "finalize",
                    monthly_refund,
                    credits_refund,
                    actual_tokens,
                ),
            )
            return reservation

    async def release(self, reservation_id: UUID) -> UsageReservation:
        async with self._lock:
            reservation = self.reservations[reservation_id]
            if reservation.status == ReservationStatus.RELEASED:
                return reservation
            if reservation.status != ReservationStatus.RESERVED:
                raise InvalidReservation(f"cannot release {reservation.status}")
            self.account.monthly_available += reservation.monthly_reserved
            self.account.credits_available += reservation.credits_reserved
            reservation.status = ReservationStatus.RELEASED
            self.entries.append(
                LedgerEntry(
                    reservation.id,
                    "release",
                    reservation.monthly_reserved,
                    reservation.credits_reserved,
                ),
            )
            return reservation

    async def reverse(self, reservation_id: UUID) -> UsageReservation:
        async with self._lock:
            reservation = self.reservations[reservation_id]
            if reservation.status == ReservationStatus.REVERSED:
                return reservation
            if reservation.status != ReservationStatus.FINALIZED:
                raise InvalidReservation(f"cannot reverse {reservation.status}")
            actual = reservation.actual_tokens or 0
            monthly_used = min(actual, reservation.monthly_reserved)
            credits_used = actual - monthly_used
            self.account.monthly_available += monthly_used
            self.account.credits_available += credits_used
            reservation.status = ReservationStatus.REVERSED
            self.entries.append(
                LedgerEntry(reservation.id, "reverse", monthly_used, credits_used, actual),
            )
            return reservation
