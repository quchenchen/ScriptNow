from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select

from scriptnow.platform.context_manifest import content_digest
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeCheckpointModel,
    CreativeContextManifestModel,
    CreativeDecisionRequestModel,
    CreativeOperationModel,
    CreativeOperationStatus,
    CreativeResumptionModel,
    CreativeResumptionStatus,
    DecisionRequestStatus,
    ProjectModel,
    ProjectRunModel,
    RunStatus,
)


class RunTransitionError(RuntimeError):
    pass


TERMINAL = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
TRANSITIONS: dict[str, set[str]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {
        RunStatus.WAITING,
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.WAITING: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED},
}


@dataclass(frozen=True, slots=True)
class RunView:
    id: str
    tenant_id: str
    project_id: str
    status: str
    state_version: int
    waiting_reason: str | None
    error_code: str | None


class RecoveryDisposition(StrEnum):
    PARKED_FOR_DECISION = "parked_for_decision"
    RESUME_FROM_CHECKPOINT = "resume_from_checkpoint"
    RETRY_FROM_MANIFEST = "retry_from_manifest"
    RECONCILE_CLAIMED_SIDE_EFFECT = "reconcile_claimed_side_effect"
    UNRECOVERABLE = "unrecoverable"


@dataclass(frozen=True, slots=True)
class RecoveryAssessment:
    run: RunView
    disposition: RecoveryDisposition
    operation_id: str | None
    decision_id: str | None
    checkpoint_id: str | None
    context_manifest_id: str | None
    reason: str


class RunCoordinator:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def enqueue(self, *, tenant_id: str, project_id: str, idempotency_key: str) -> RunView:
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(ProjectRunModel).where(
                        ProjectRunModel.tenant_id == tenant_id,
                        ProjectRunModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                if existing.project_id != project_id:
                    raise RunTransitionError("idempotency key belongs to another project")
                return self._view(existing)
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise RunTransitionError("project is outside tenant scope")
            run = ProjectRunModel(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
            )
            session.add(run)
            await session.flush()
            return self._view(run)

    async def transition(
        self,
        *,
        tenant_id: str,
        run_id: str,
        target: RunStatus,
        waiting_reason: str | None = None,
        error_code: str | None = None,
    ) -> RunView:
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise RunTransitionError("run is outside tenant scope")
            if target not in TRANSITIONS.get(run.status, set()):
                raise RunTransitionError(f"invalid run transition: {run.status} -> {target}")
            if target == RunStatus.WAITING and not waiting_reason:
                raise RunTransitionError("waiting transition requires a reason")
            if target == RunStatus.FAILED and not error_code:
                raise RunTransitionError("failed transition requires an error code")
            run.status = target
            run.waiting_reason = waiting_reason if target == RunStatus.WAITING else None
            run.error_code = error_code if target == RunStatus.FAILED else None
            run.state_version += 1
            await session.flush()
            return self._view(run)

    async def recoverable(self) -> list[RunView]:
        async with self.database.session() as session:
            runs = (
                await session.scalars(
                    select(ProjectRunModel)
                    .where(
                        ProjectRunModel.status.in_(
                            [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING]
                        )
                    )
                    .order_by(ProjectRunModel.created_at)
                )
            ).all()
            return [self._view(run) for run in runs]

    async def recovery_matrix(self) -> list[RecoveryAssessment]:
        """Classify every active run using only durable state.

        The result is safe to evaluate in a fresh process. In particular, a
        claimed resumption is never automatically replayed because the previous
        process may have crossed the external side-effect boundary.
        """
        async with self.database.session() as session:
            runs = list(
                await session.scalars(
                    select(ProjectRunModel)
                    .where(
                        ProjectRunModel.status.in_(
                            [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING]
                        )
                    )
                    .order_by(ProjectRunModel.created_at)
                )
            )
            return [await self._assess(session, run) for run in runs]

    async def reconcile_interrupted(self) -> list[RecoveryAssessment]:
        """Apply the durable recovery matrix after a process restart."""
        async with self.database.session() as session:
            runs = list(
                await session.scalars(
                    select(ProjectRunModel)
                    .where(
                        ProjectRunModel.status.in_(
                            [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING]
                        )
                    )
                    .order_by(ProjectRunModel.created_at)
                )
            )
            assessments: list[RecoveryAssessment] = []
            for run in runs:
                assessment = await self._assess(session, run)
                assessments.append(assessment)
                if assessment.disposition == RecoveryDisposition.PARKED_FOR_DECISION:
                    target_status = RunStatus.WAITING
                    waiting_reason = "decision_required"
                    error_code = None
                elif assessment.disposition in {
                    RecoveryDisposition.RESUME_FROM_CHECKPOINT,
                    RecoveryDisposition.RETRY_FROM_MANIFEST,
                }:
                    target_status = RunStatus.QUEUED
                    waiting_reason = None
                    error_code = None
                elif (
                    assessment.disposition
                    == RecoveryDisposition.RECONCILE_CLAIMED_SIDE_EFFECT
                ):
                    target_status = RunStatus.WAITING
                    waiting_reason = "side_effect_reconciliation"
                    error_code = None
                else:
                    target_status = RunStatus.FAILED
                    waiting_reason = None
                    error_code = "recovery_state_incomplete"
                if (
                    run.status != target_status
                    or run.waiting_reason != waiting_reason
                    or run.error_code != error_code
                ):
                    run.status = target_status
                    run.waiting_reason = waiting_reason
                    run.error_code = error_code
                    run.state_version += 1
                operation = (
                    await session.scalars(
                        select(CreativeOperationModel).where(
                            CreativeOperationModel.run_id == run.id
                        )
                    )
                ).one_or_none()
                if operation is not None:
                    if target_status == RunStatus.QUEUED:
                        operation.status = CreativeOperationStatus.QUEUED
                    elif target_status == RunStatus.WAITING:
                        operation.status = CreativeOperationStatus.WAITING_FOR_DECISION
                    elif target_status == RunStatus.FAILED:
                        operation.status = CreativeOperationStatus.FAILED
                        operation.error_code = error_code
            await session.flush()
            return assessments

    async def _assess(self, session: object, run: ProjectRunModel) -> RecoveryAssessment:
        operation = (
            await session.scalars(
                select(CreativeOperationModel).where(
                    CreativeOperationModel.run_id == run.id,
                    CreativeOperationModel.tenant_id == run.tenant_id,
                )
            )
        ).one_or_none()
        if operation is None:
            return self._assessment(
                run,
                RecoveryDisposition.UNRECOVERABLE,
                reason="run has no persisted creative operation",
            )

        resumption = (
            await session.scalars(
                select(CreativeResumptionModel)
                .where(CreativeResumptionModel.operation_id == operation.id)
                .order_by(CreativeResumptionModel.claimed_at.desc())
            )
        ).first()
        if (
            resumption is not None
            and resumption.status == CreativeResumptionStatus.CLAIMED
        ):
            return self._assessment(
                run,
                RecoveryDisposition.RECONCILE_CLAIMED_SIDE_EFFECT,
                operation=operation,
                checkpoint_id=resumption.checkpoint_id,
                decision_id=resumption.decision_request_id,
                reason="resumption was claimed before restart",
            )

        decision = (
            await session.scalars(
                select(CreativeDecisionRequestModel)
                .where(CreativeDecisionRequestModel.operation_id == operation.id)
                .order_by(CreativeDecisionRequestModel.created_at.desc())
            )
        ).first()
        checkpoint = None
        if decision is not None and decision.checkpoint_id is not None:
            checkpoint = await session.get(CreativeCheckpointModel, decision.checkpoint_id)
            if (
                checkpoint is None
                or checkpoint.operation_id != operation.id
                or not checkpoint.is_complete
            ):
                checkpoint = None
        if decision is not None and checkpoint is not None:
            if decision.status == DecisionRequestStatus.PENDING:
                return self._assessment(
                    run,
                    RecoveryDisposition.PARKED_FOR_DECISION,
                    operation=operation,
                    decision_id=decision.id,
                    checkpoint_id=checkpoint.id,
                    reason="complete checkpoint is waiting for a user decision",
                )
            if decision.status in {
                DecisionRequestStatus.APPROVED,
                DecisionRequestStatus.REJECTED,
            }:
                return self._assessment(
                    run,
                    RecoveryDisposition.RESUME_FROM_CHECKPOINT,
                    operation=operation,
                    decision_id=decision.id,
                    checkpoint_id=checkpoint.id,
                    reason="resolved decision has a complete AgentScope checkpoint",
                )

        manifest = None
        if operation.context_manifest_id is not None:
            candidate = await session.get(
                CreativeContextManifestModel, operation.context_manifest_id
            )
            if (
                candidate is not None
                and candidate.tenant_id == run.tenant_id
                and candidate.project_id == run.project_id
                and content_digest(candidate.content) == candidate.content_digest
            ):
                manifest = candidate
        if manifest is not None:
            return self._assessment(
                run,
                RecoveryDisposition.RETRY_FROM_MANIFEST,
                operation=operation,
                context_manifest_id=manifest.id,
                reason="immutable Context Manifest can reproduce the operation input",
            )
        return self._assessment(
            run,
            RecoveryDisposition.UNRECOVERABLE,
            operation=operation,
            decision_id=decision.id if decision is not None else None,
            reason="neither a complete checkpoint nor a valid Context Manifest exists",
        )

    @classmethod
    def _assessment(
        cls,
        run: ProjectRunModel,
        disposition: RecoveryDisposition,
        *,
        operation: CreativeOperationModel | None = None,
        decision_id: str | None = None,
        checkpoint_id: str | None = None,
        context_manifest_id: str | None = None,
        reason: str,
    ) -> RecoveryAssessment:
        return RecoveryAssessment(
            run=cls._view(run),
            disposition=disposition,
            operation_id=operation.id if operation is not None else None,
            decision_id=decision_id,
            checkpoint_id=checkpoint_id,
            context_manifest_id=context_manifest_id,
            reason=reason,
        )

    @staticmethod
    def _view(run: ProjectRunModel) -> RunView:
        return RunView(
            id=run.id,
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            status=str(run.status),
            state_version=run.state_version,
            waiting_reason=run.waiting_reason,
            error_code=run.error_code,
        )

    async def status(self, *, tenant_id: str, run_id: str) -> RunView | None:
        """Return current run status or None if not found."""
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                return None
            return self._view(run)
