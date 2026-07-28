import pytest

from scriptnow.platform.creative_operations import CreativeOperationStore
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    DecisionRequestStatus,
    ProjectMedium,
    ProjectModel,
    RunStatus,
    TenantModel,
)
from scriptnow.platform.run_coordinator import (
    RecoveryDisposition,
    RunCoordinator,
    RunTransitionError,
)


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


@pytest.mark.asyncio
async def test_restart_reconciliation_uses_manifest_and_checkpoint_matrix(
    coordinator_data: tuple[RunCoordinator, Database, TenantModel, ProjectModel],
) -> None:
    coordinator, database, tenant, project = coordinator_data
    operations = CreativeOperationStore(database)
    session_id = await operations.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="script",
    )

    async def operation_for(key: str, *, waiting: bool = False):
        run = await coordinator.enqueue(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key=f"{key}-run",
        )
        await coordinator.transition(
            tenant_id=tenant.id,
            run_id=run.id,
            target=RunStatus.RUNNING,
        )
        operation = await operations.enqueue_operation(
            tenant_id=tenant.id,
            session_id=session_id,
            turn_id=None,
            run_id=run.id,
            command="script.write",
            domain="script",
            stage=key,
            idempotency_key=f"{key}-operation",
            policy_snapshot={"schema_version": 1},
        )
        if waiting:
            await coordinator.transition(
                tenant_id=tenant.id,
                run_id=run.id,
                target=RunStatus.WAITING,
                waiting_reason="decision_required",
            )
        return run, operation

    retry_run, _ = await operation_for("retry")
    parked_run, parked_operation = await operation_for("parked", waiting=True)
    parked_stage = await operations.start_stage(
        tenant_id=tenant.id,
        operation_id=parked_operation.id,
        stage_key="parked",
        attempt=1,
        input_digest="parked-input",
    )
    parked_checkpoint = await operations.save_checkpoint(
        tenant_id=tenant.id,
        operation_id=parked_operation.id,
        stage_run_id=parked_stage,
        checkpoint_key="parked-checkpoint",
        state_format="agentscope-agent-state-json-v1",
        state_payload=b'{"version":1}',
        resume_metadata={"reply_id": "reply-1"},
        is_complete=True,
    )
    await operations.request_decision(
        tenant_id=tenant.id,
        operation_id=parked_operation.id,
        stage_run_id=parked_stage,
        artifact_ref_id=None,
        checkpoint_id=parked_checkpoint,
        kind="tool_confirmation",
        prompt="Allow this tool call?",
        options=[{"key": "approve"}, {"key": "reject"}],
        impact={"side_effect": True},
        idempotency_key="parked-decision",
    )

    restarted = RunCoordinator(database)
    reconciled = await restarted.reconcile_interrupted()

    by_run = {item.run.id: item for item in reconciled}
    assert by_run[retry_run.id].disposition == RecoveryDisposition.RETRY_FROM_MANIFEST
    assert by_run[retry_run.id].context_manifest_id is not None
    assert by_run[parked_run.id].disposition == RecoveryDisposition.PARKED_FOR_DECISION
    statuses = {run.id: run for run in await restarted.recoverable()}
    assert statuses[retry_run.id].status == RunStatus.QUEUED
    assert statuses[parked_run.id].status == RunStatus.WAITING
    assert statuses[parked_run.id].waiting_reason == "decision_required"


@pytest.mark.asyncio
async def test_restart_never_replays_claimed_side_effect(
    coordinator_data: tuple[RunCoordinator, Database, TenantModel, ProjectModel],
) -> None:
    coordinator, database, tenant, project = coordinator_data
    operations = CreativeOperationStore(database)
    session_id = await operations.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="script",
    )
    run = await coordinator.enqueue(
        tenant_id=tenant.id,
        project_id=project.id,
        idempotency_key="claimed-run",
    )
    await coordinator.transition(
        tenant_id=tenant.id,
        run_id=run.id,
        target=RunStatus.RUNNING,
    )
    operation = await operations.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=run.id,
        command="script.write",
        domain="script",
        stage="write",
        idempotency_key="claimed-operation",
        policy_snapshot={"schema_version": 1},
    )
    stage_id = await operations.start_stage(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_key="write",
        attempt=1,
        input_digest="claimed-input",
    )
    checkpoint_id = await operations.save_checkpoint(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        checkpoint_key="claimed-checkpoint",
        state_format="agentscope-agent-state-json-v1",
        state_payload=b'{"version":1}',
        resume_metadata={"reply_id": "reply-2"},
        is_complete=True,
    )
    decision = await operations.request_decision(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        artifact_ref_id=None,
        checkpoint_id=checkpoint_id,
        kind="tool_confirmation",
        prompt="Allow this tool call?",
        options=[{"key": "approve"}, {"key": "reject"}],
        impact={"side_effect": True},
        idempotency_key="claimed-decision",
    )
    await operations.resolve_decision(
        tenant_id=tenant.id,
        decision_id=decision.id,
        status=DecisionRequestStatus.APPROVED,
        decision={"key": "approve"},
        decided_by={"type": "user", "id": "creator"},
    )
    await operations.claim_resumption(
        tenant_id=tenant.id,
        decision_id=decision.id,
        idempotency_key="claimed-resume",
        claimed_by={"worker_id": "worker-before-restart"},
    )

    [assessment] = await RunCoordinator(database).reconcile_interrupted()

    assert (
        assessment.disposition
        == RecoveryDisposition.RECONCILE_CLAIMED_SIDE_EFFECT
    )
    [recovered] = await coordinator.recoverable()
    assert recovered.status == RunStatus.WAITING
    assert recovered.waiting_reason == "side_effect_reconciliation"
