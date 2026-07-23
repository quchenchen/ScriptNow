import pytest

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import ProjectMedium, ProjectModel, RunStatus, TenantModel
from scriptflow_v7.platform.run_coordinator import RunCoordinator, RunTransitionError


@pytest.fixture
async def coordinator_data() -> tuple[RunCoordinator, Database, TenantModel, ProjectModel]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Story", medium=ProjectMedium.SCRIPT)
        session.add(project)
        await session.flush()
    yield RunCoordinator(database), database, tenant, project
    await database.dispose()


@pytest.mark.asyncio
async def test_run_lifecycle_wait_resume_and_recovery(
    coordinator_data: tuple[RunCoordinator, Database, TenantModel, ProjectModel],
) -> None:
    coordinator, _, tenant, project = coordinator_data
    queued = await coordinator.enqueue(
        tenant_id=tenant.id, project_id=project.id, idempotency_key="make-outline"
    )
    running = await coordinator.transition(
        tenant_id=tenant.id, run_id=queued.id, target=RunStatus.RUNNING
    )
    waiting = await coordinator.transition(
        tenant_id=tenant.id,
        run_id=queued.id,
        target=RunStatus.WAITING,
        waiting_reason="tool_confirmation",
    )
    assert [run.id for run in await coordinator.recoverable()] == [queued.id]
    resumed = await coordinator.transition(
        tenant_id=tenant.id, run_id=queued.id, target=RunStatus.RUNNING
    )
    succeeded = await coordinator.transition(
        tenant_id=tenant.id, run_id=queued.id, target=RunStatus.SUCCEEDED
    )

    assert [
        running.state_version,
        waiting.state_version,
        resumed.state_version,
        succeeded.state_version,
    ] == [2, 3, 4, 5]
    assert await coordinator.recoverable() == []


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_and_tenant_scoped(
    coordinator_data: tuple[RunCoordinator, Database, TenantModel, ProjectModel],
) -> None:
    coordinator, database, tenant, project = coordinator_data
    first = await coordinator.enqueue(
        tenant_id=tenant.id, project_id=project.id, idempotency_key="same"
    )
    repeated = await coordinator.enqueue(
        tenant_id=tenant.id, project_id=project.id, idempotency_key="same"
    )
    assert repeated == first

    async with database.session() as session:
        other = TenantModel(name="Other")
        session.add(other)
        await session.flush()
    with pytest.raises(RunTransitionError, match="outside tenant scope"):
        await coordinator.enqueue(
            tenant_id=other.id, project_id=project.id, idempotency_key="attack"
        )
    with pytest.raises(RunTransitionError, match="outside tenant scope"):
        await coordinator.transition(tenant_id=other.id, run_id=first.id, target=RunStatus.RUNNING)


@pytest.mark.asyncio
async def test_invalid_and_incomplete_transitions_are_rejected(
    coordinator_data: tuple[RunCoordinator, Database, TenantModel, ProjectModel],
) -> None:
    coordinator, _, tenant, project = coordinator_data
    run = await coordinator.enqueue(
        tenant_id=tenant.id, project_id=project.id, idempotency_key="invalid"
    )
    with pytest.raises(RunTransitionError, match="invalid run transition"):
        await coordinator.transition(tenant_id=tenant.id, run_id=run.id, target=RunStatus.SUCCEEDED)
    await coordinator.transition(tenant_id=tenant.id, run_id=run.id, target=RunStatus.RUNNING)
    with pytest.raises(RunTransitionError, match="requires a reason"):
        await coordinator.transition(tenant_id=tenant.id, run_id=run.id, target=RunStatus.WAITING)
