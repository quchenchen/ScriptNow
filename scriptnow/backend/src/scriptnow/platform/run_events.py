import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectRunModel, RunStreamEventModel

_RUN_APPEND_LOCKS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


class RunEventType(StrEnum):
    AGENT = "agent"
    CONVERSATION = "conversation"
    NODE = "node"
    DECISION = "decision"
    SYSTEM = "system"
    HEARTBEAT = "heartbeat"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: str | None
    sequence: int
    event_key: str
    type: RunEventType
    payload: dict[str, Any]
    occurred_at: datetime

    @property
    def cursor(self) -> str:
        return str(self.sequence)


class InMemoryRunEventLog:
    """Executable protocol model for P0; persistent storage replaces it in P1."""

    def __init__(self) -> None:
        self._events: dict[str, list[RunEvent]] = defaultdict(list)
        self._keys: set[tuple[str, str]] = set()

    def append(
        self,
        *,
        run_id: str,
        event_key: str,
        type: RunEventType,
        payload: dict[str, Any],
    ) -> RunEvent:
        dedupe_key = (run_id, event_key)
        if dedupe_key in self._keys:
            return next(event for event in self._events[run_id] if event.event_key == event_key)

        event = RunEvent(
            run_id=run_id,
            sequence=len(self._events[run_id]) + 1,
            event_key=event_key,
            type=type,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        self._keys.add(dedupe_key)
        self._events[run_id].append(event)
        return event

    def after(self, run_id: str, cursor: str | None) -> list[RunEvent]:
        sequence = int(cursor) if cursor is not None else 0
        return [event for event in self._events[run_id] if event.sequence > sequence]


def encode_sse(event: RunEvent) -> str:
    import json

    data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.cursor}\nevent: {event.type.value}\ndata: {data}\n\n"


class PersistentRunEventLog:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def append(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_key: str,
        type: RunEventType,
        payload: dict[str, Any],
        correlation_id: str,
    ) -> RunEvent:
        # One AgentScope reply can bridge thinking, tool, and text events from
        # concurrent tasks. Allocate sequence numbers serially per run across all
        # event-log instances in this process so two sessions cannot observe the
        # same MAX(sequence).
        async with _RUN_APPEND_LOCKS[run_id], self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise ValueError("run is outside tenant scope")
            existing = (
                await session.scalars(
                    select(RunStreamEventModel).where(
                        RunStreamEventModel.run_id == run_id,
                        RunStreamEventModel.event_key == event_key,
                    )
                )
            ).one_or_none()
            if existing:
                return self._event(existing)
            last = await session.scalar(
                select(func.max(RunStreamEventModel.sequence)).where(
                    RunStreamEventModel.run_id == run_id
                )
            )
            record = RunStreamEventModel(
                tenant_id=tenant_id,
                project_id=run.project_id,
                run_id=run_id,
                sequence=(last or 0) + 1,
                event_key=event_key,
                event_type=type,
                correlation_id=correlation_id,
                payload=payload,
            )
            session.add(record)
            await session.flush()
            return self._event(record)

    async def after(self, *, tenant_id: str, run_id: str, cursor: str | None) -> list[RunEvent]:
        try:
            sequence = int(cursor) if cursor else 0
        except ValueError as error:
            raise ValueError("invalid event cursor") from error
        if sequence < 0:
            raise ValueError("invalid event cursor")
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise ValueError("run is outside tenant scope")
            records = (
                await session.scalars(
                    select(RunStreamEventModel)
                    .where(
                        RunStreamEventModel.run_id == run_id,
                        RunStreamEventModel.sequence > sequence,
                    )
                    .order_by(RunStreamEventModel.sequence)
                )
            ).all()
            return [self._event(record) for record in records]

    @staticmethod
    def _event(record: RunStreamEventModel) -> RunEvent:
        occurred_at = record.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        return RunEvent(
            run_id=record.run_id,
            sequence=record.sequence,
            event_key=record.event_key,
            type=RunEventType(record.event_type),
            payload=dict(record.payload),
            occurred_at=occurred_at,
        )
