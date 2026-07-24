from time import perf_counter

import pytest

from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectModel,
    ProjectRunModel,
    RunStreamEventModel,
    TenantModel,
)
from scriptnow.platform.run_events import PersistentRunEventLog


@pytest.mark.asyncio
async def test_event_incremental_query_p95_is_below_200ms() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Performance Studio")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id, name="Large Project", medium="script", source_mode="original"
        )
        session.add(project)
        await session.flush()
        run = ProjectRunModel(
            tenant_id=tenant.id, project_id=project.id, idempotency_key="performance-run"
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                RunStreamEventModel(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    run_id=run.id,
                    sequence=index,
                    event_key=f"event-{index}",
                    event_type="node",
                    correlation_id="performance",
                    payload={"index": index},
                )
                for index in range(1, 1001)
            ]
        )
        tenant_id, run_id = tenant.id, run.id
    event_log = PersistentRunEventLog(database)
    timings = []
    for _ in range(20):
        started = perf_counter()
        events = await event_log.after(tenant_id=tenant_id, run_id=run_id, cursor="950")
        timings.append((perf_counter() - started) * 1000)
    assert len(events) == 50
    assert sorted(timings)[18] < 200
    await database.dispose()
