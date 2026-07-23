import asyncio

import pytest
from sqlalchemy import select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    RunStreamEventModel,
    TenantModel,
)
from scriptflow_v7.platform.run_events import PersistentRunEventLog, RunEventType, encode_sse


@pytest.fixture
async def event_data() -> tuple[PersistentRunEventLog, Database, TenantModel, ProjectRunModel]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Story", medium=ProjectMedium.NOVEL)
        session.add(project)
        await session.flush()
        run = ProjectRunModel(tenant_id=tenant.id, project_id=project.id, idempotency_key="run")
        session.add(run)
        await session.flush()
    yield PersistentRunEventLog(database), database, tenant, run
    await database.dispose()


@pytest.mark.asyncio
async def test_persistent_event_dedupe_cursor_and_sse_reconnect(
    event_data: tuple[PersistentRunEventLog, Database, TenantModel, ProjectRunModel],
) -> None:
    log, _, tenant, run = event_data
    first = await log.append(
        tenant_id=tenant.id,
        run_id=run.id,
        event_key="reply-1",
        type=RunEventType.AGENT,
        payload={"delta": "开"},
        correlation_id="trace-1",
    )
    duplicate = await log.append(
        tenant_id=tenant.id,
        run_id=run.id,
        event_key="reply-1",
        type=RunEventType.AGENT,
        payload={"delta": "ignored"},
        correlation_id="trace-1",
    )
    terminal = await log.append(
        tenant_id=tenant.id,
        run_id=run.id,
        event_key="terminal-1",
        type=RunEventType.TERMINAL,
        payload={"status": "succeeded"},
        correlation_id="trace-1",
    )

    assert duplicate == first
    assert terminal.sequence == 2
    resumed = await log.after(tenant_id=tenant.id, run_id=run.id, cursor=first.cursor)
    assert resumed == [terminal]
    assert encode_sse(resumed[0]).startswith("id: 2\nevent: terminal\n")


@pytest.mark.asyncio
async def test_persistent_event_sequence_allocation_is_safe_under_concurrency(
    event_data: tuple[PersistentRunEventLog, Database, TenantModel, ProjectRunModel],
) -> None:
    log, database, tenant, run = event_data

    events = await asyncio.gather(
        *(
            log.append(
                tenant_id=tenant.id,
                run_id=run.id,
                event_key=f"delta-{index}",
                type=RunEventType.CONVERSATION,
                payload={"delta": str(index)},
                correlation_id="trace-concurrent",
            )
            for index in range(50)
        )
    )

    assert sorted(event.sequence for event in events) == list(range(1, 51))
    async with database.session() as session:
        stored = (
            await session.scalars(
                select(RunStreamEventModel)
                .where(RunStreamEventModel.run_id == run.id)
                .order_by(RunStreamEventModel.sequence)
            )
        ).all()
    assert [record.sequence for record in stored] == list(range(1, 51))


@pytest.mark.asyncio
async def test_event_log_rejects_cross_tenant_and_bad_cursor(
    event_data: tuple[PersistentRunEventLog, Database, TenantModel, ProjectRunModel],
) -> None:
    log, _, _, run = event_data
    with pytest.raises(ValueError, match="tenant scope"):
        await log.after(tenant_id="other", run_id=run.id, cursor=None)
    with pytest.raises(ValueError, match="invalid event cursor"):
        await log.after(tenant_id=run.tenant_id, run_id=run.id, cursor="NaN")


@pytest.mark.asyncio
async def test_project_events_are_append_only(
    event_data: tuple[PersistentRunEventLog, Database, TenantModel, ProjectRunModel],
) -> None:
    log, database, tenant, run = event_data
    event = await log.append(
        tenant_id=tenant.id,
        run_id=run.id,
        event_key="one",
        type=RunEventType.AGENT,
        payload={},
        correlation_id="trace",
    )
    async with database.session() as session:
        record = await session.scalar(
            select(RunStreamEventModel).where(
                RunStreamEventModel.run_id == run.id,
                RunStreamEventModel.sequence == event.sequence,
            )
        )
        assert record is not None
        record.payload = {"tampered": True}
        with pytest.raises(ValueError, match="append-only"):
            await session.flush()
        await session.rollback()
