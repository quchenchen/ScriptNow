from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeArtifactRefModel,
    CreativeCheckpointModel,
    CreativeDecisionRequestModel,
    CreativeOperationModel,
    CreativeOperationStatus,
    CreativeSessionModel,
    CreativeSessionStatus,
    CreativeStageRunModel,
    CreativeStageStatus,
    CreativeTurnModel,
    DecisionRequestStatus,
    ProjectModel,
    ProjectRunModel,
    utc_now,
)


class CreativeOperationError(RuntimeError):
    pass


def coherent_run_status(
    run_status: object,
    operation_status: object | None,
) -> str:
    """Keep the public run state coherent with its persisted operation lineage."""
    run_value = str(run_status)
    if operation_status is None:
        return run_value
    operation_value = str(operation_status)
    terminal = {"succeeded", "failed", "cancelled"}
    if run_value in terminal and operation_value not in terminal:
        if operation_value == "waiting_for_user":
            return "waiting_for_user"
        if operation_value == "queued":
            return "queued"
        return "running"
    if run_value == "succeeded" and operation_value in {"failed", "cancelled"}:
        return operation_value
    return run_value


@dataclass(frozen=True, slots=True)
class OperationView:
    id: str
    session_id: str
    run_id: str | None
    command: str
    domain: str
    stage: str
    status: str


@dataclass(frozen=True, slots=True)
class DecisionView:
    id: str
    operation_id: str
    stage_run_id: str | None
    status: str
    decision: dict[str, object] | None
    decided_at: datetime | None


class CreativeOperationStore:
    """Persist shared execution lineage without owning domain artifacts."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def open_session(
        self, *, tenant_id: str, project_id: str, active_domain: str
    ) -> str:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise CreativeOperationError("project is outside tenant scope")
            creative_session = CreativeSessionModel(
                tenant_id=tenant_id,
                project_id=project_id,
                active_domain=active_domain,
            )
            session.add(creative_session)
            await session.flush()
            return creative_session.id

    async def get_or_open_session(
        self, *, tenant_id: str, project_id: str, active_domain: str
    ) -> str:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise CreativeOperationError("project is outside tenant scope")
            existing = (
                await session.scalars(
                    select(CreativeSessionModel)
                    .where(
                        CreativeSessionModel.tenant_id == tenant_id,
                        CreativeSessionModel.project_id == project_id,
                        CreativeSessionModel.active_domain == active_domain,
                        CreativeSessionModel.status == CreativeSessionStatus.ACTIVE,
                    )
                    .order_by(CreativeSessionModel.created_at.desc())
                )
            ).first()
            if existing is not None:
                return existing.id
            creative_session = CreativeSessionModel(
                tenant_id=tenant_id,
                project_id=project_id,
                active_domain=active_domain,
            )
            session.add(creative_session)
            await session.flush()
            return creative_session.id

    async def append_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        actor: dict[str, object],
        input: dict[str, object],
    ) -> str:
        async with self.database.session() as session:
            creative_session = await self._owned_session(session, tenant_id, session_id)
            turn = CreativeTurnModel(session_id=creative_session.id, actor=actor, input=input)
            session.add(turn)
            await session.flush()
            return turn.id

    async def enqueue_operation(
        self,
        *,
        tenant_id: str,
        session_id: str,
        turn_id: str | None,
        run_id: str | None,
        command: str,
        domain: str,
        stage: str,
        idempotency_key: str,
        policy_snapshot: dict[str, object],
        context_manifest_id: str | None = None,
    ) -> OperationView:
        async with self.database.session() as session:
            creative_session = await self._owned_session(session, tenant_id, session_id)
            existing = (
                await session.scalars(
                    select(CreativeOperationModel).where(
                        CreativeOperationModel.session_id == session_id,
                        CreativeOperationModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return self._operation_view(existing)
            if turn_id is not None:
                turn = await session.get(CreativeTurnModel, turn_id)
                if turn is None or turn.session_id != session_id:
                    raise CreativeOperationError("turn is outside creative session")
            if run_id is not None:
                run = await session.get(ProjectRunModel, run_id)
                if (
                    run is None
                    or run.tenant_id != tenant_id
                    or run.project_id != creative_session.project_id
                ):
                    raise CreativeOperationError("run is outside creative session")
            operation = CreativeOperationModel(
                tenant_id=tenant_id,
                project_id=creative_session.project_id,
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                command=command,
                domain=domain,
                stage=stage,
                idempotency_key=idempotency_key,
                policy_snapshot=policy_snapshot,
                context_manifest_id=context_manifest_id,
            )
            session.add(operation)
            await session.flush()
            return self._operation_view(operation)

    async def start_stage(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        stage_key: str,
        attempt: int,
        input_digest: str,
    ) -> str:
        if attempt < 1:
            raise CreativeOperationError("stage attempt must be positive")
        async with self.database.session() as session:
            operation = await self._owned_operation(session, tenant_id, operation_id)
            existing = (
                await session.scalars(
                    select(CreativeStageRunModel).where(
                        CreativeStageRunModel.operation_id == operation_id,
                        CreativeStageRunModel.stage_key == stage_key,
                        CreativeStageRunModel.attempt == attempt,
                    )
                )
            ).one_or_none()
            if existing is not None:
                if existing.input_digest != input_digest:
                    raise CreativeOperationError("stage attempt input does not match")
                return existing.id
            stage = CreativeStageRunModel(
                operation_id=operation.id,
                stage_key=stage_key,
                status=CreativeStageStatus.RUNNING,
                attempt=attempt,
                input_digest=input_digest,
                started_at=utc_now(),
            )
            operation.stage = stage_key
            operation.status = CreativeOperationStatus.RUNNING
            session.add(stage)
            await session.flush()
            return stage.id

    async def save_checkpoint(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        stage_run_id: str,
        checkpoint_key: str,
        state_format: str,
        state_payload: bytes,
        resume_metadata: dict[str, object],
        is_complete: bool,
    ) -> str:
        async with self.database.session() as session:
            await self._owned_operation(session, tenant_id, operation_id)
            stage = await session.get(CreativeStageRunModel, stage_run_id)
            if stage is None or stage.operation_id != operation_id:
                raise CreativeOperationError("stage is outside operation")
            existing = (
                await session.scalars(
                    select(CreativeCheckpointModel).where(
                        CreativeCheckpointModel.operation_id == operation_id,
                        CreativeCheckpointModel.checkpoint_key == checkpoint_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                if (
                    existing.state_format != state_format
                    or existing.state_payload != state_payload
                    or existing.resume_metadata != resume_metadata
                    or existing.is_complete != is_complete
                ):
                    raise CreativeOperationError("checkpoint key belongs to different state")
                return existing.id
            checkpoint = CreativeCheckpointModel(
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                checkpoint_key=checkpoint_key,
                state_format=state_format,
                state_payload=state_payload,
                resume_metadata=resume_metadata,
                is_complete=is_complete,
            )
            session.add(checkpoint)
            await session.flush()
            return checkpoint.id

    async def register_artifact(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        stage_run_id: str,
        domain: str,
        artifact_type: str,
        artifact_id: str,
        revision: int,
        status: str,
        schema_version: int,
        input_digest: str,
        dependency_versions: dict[str, object],
        provenance: dict[str, object],
    ) -> str:
        if revision < 1 or schema_version < 1:
            raise CreativeOperationError("artifact versions must be positive")
        async with self.database.session() as session:
            await self._owned_operation(session, tenant_id, operation_id)
            stage = await session.get(CreativeStageRunModel, stage_run_id)
            if stage is None or stage.operation_id != operation_id:
                raise CreativeOperationError("stage is outside operation")
            existing = (
                await session.scalars(
                    select(CreativeArtifactRefModel).where(
                        CreativeArtifactRefModel.operation_id == operation_id,
                        CreativeArtifactRefModel.domain == domain,
                        CreativeArtifactRefModel.artifact_type == artifact_type,
                        CreativeArtifactRefModel.artifact_id == artifact_id,
                        CreativeArtifactRefModel.revision == revision,
                    )
                )
            ).one_or_none()
            if existing is not None:
                if (
                    existing.input_digest != input_digest
                    or existing.provenance != provenance
                    or existing.dependency_versions != dependency_versions
                ):
                    raise CreativeOperationError("artifact revision provenance does not match")
                return existing.id
            artifact = CreativeArtifactRefModel(
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                domain=domain,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                revision=revision,
                status=status,
                schema_version=schema_version,
                input_digest=input_digest,
                dependency_versions=dependency_versions,
                provenance=provenance,
            )
            session.add(artifact)
            await session.flush()
            return artifact.id

    async def request_decision(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        stage_run_id: str,
        artifact_ref_id: str | None,
        checkpoint_id: str | None,
        kind: str,
        prompt: str,
        options: list[dict[str, object]],
        impact: dict[str, object],
        idempotency_key: str,
    ) -> DecisionView:
        async with self.database.session() as session:
            operation = await self._owned_operation(session, tenant_id, operation_id)
            stage = await session.get(CreativeStageRunModel, stage_run_id)
            if stage is None or stage.operation_id != operation_id:
                raise CreativeOperationError("stage is outside operation")
            await self._validate_optional_refs(
                session,
                operation_id=operation_id,
                artifact_ref_id=artifact_ref_id,
                checkpoint_id=checkpoint_id,
            )
            existing = (
                await session.scalars(
                    select(CreativeDecisionRequestModel).where(
                        CreativeDecisionRequestModel.operation_id == operation_id,
                        CreativeDecisionRequestModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return self._decision_view(existing)
            decision = CreativeDecisionRequestModel(
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                artifact_ref_id=artifact_ref_id,
                checkpoint_id=checkpoint_id,
                kind=kind,
                prompt=prompt,
                options=options,
                impact=impact,
                idempotency_key=idempotency_key,
            )
            stage.status = CreativeStageStatus.WAITING_FOR_DECISION
            operation.status = CreativeOperationStatus.WAITING_FOR_DECISION
            session.add(decision)
            await session.flush()
            return self._decision_view(decision)

    async def resolve_decision(
        self,
        *,
        tenant_id: str,
        decision_id: str,
        status: DecisionRequestStatus,
        decision: dict[str, object],
        decided_by: dict[str, object],
    ) -> DecisionView:
        if status not in {DecisionRequestStatus.APPROVED, DecisionRequestStatus.REJECTED}:
            raise CreativeOperationError("decision must be approved or rejected")
        async with self.database.session() as session:
            item = await session.get(CreativeDecisionRequestModel, decision_id)
            if item is None:
                raise CreativeOperationError("decision does not exist")
            operation = await self._owned_operation(session, tenant_id, item.operation_id)
            if item.status != DecisionRequestStatus.PENDING:
                if (
                    item.status == status
                    and item.decision == decision
                    and item.decided_by == decided_by
                ):
                    return self._decision_view(item)
                raise CreativeOperationError("decision has already been resolved")
            item.status = status
            item.decision = decision
            item.decided_by = decided_by
            item.decided_at = utc_now()
            operation.status = CreativeOperationStatus.RUNNING
            if item.stage_run_id is not None:
                stage = await session.get(CreativeStageRunModel, item.stage_run_id)
                if stage is not None:
                    stage.status = CreativeStageStatus.RUNNING
            await session.flush()
            return self._decision_view(item)

    async def pending_decision_for_run(
        self, *, tenant_id: str, run_id: str
    ) -> DecisionView | None:
        async with self.database.session() as session:
            operation = (
                await session.scalars(
                    select(CreativeOperationModel).where(
                        CreativeOperationModel.tenant_id == tenant_id,
                        CreativeOperationModel.run_id == run_id,
                    )
                )
            ).one_or_none()
            if operation is None:
                return None
            item = (
                await session.scalars(
                    select(CreativeDecisionRequestModel)
                    .where(
                        CreativeDecisionRequestModel.operation_id == operation.id,
                        CreativeDecisionRequestModel.status == DecisionRequestStatus.PENDING,
                    )
                    .order_by(CreativeDecisionRequestModel.created_at.desc())
                )
            ).first()
            return self._decision_view(item) if item is not None else None

    async def operation_for_run(
        self, *, tenant_id: str, run_id: str
    ) -> OperationView | None:
        async with self.database.session() as session:
            operation = (
                await session.scalars(
                    select(CreativeOperationModel).where(
                        CreativeOperationModel.tenant_id == tenant_id,
                        CreativeOperationModel.run_id == run_id,
                    )
                )
            ).one_or_none()
            return self._operation_view(operation) if operation is not None else None

    async def finish_stage(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        stage_run_id: str,
        status: CreativeStageStatus,
        error: dict[str, object] | None = None,
    ) -> OperationView:
        if status not in {
            CreativeStageStatus.READY,
            CreativeStageStatus.FAILED,
            CreativeStageStatus.CANCELLED,
        }:
            raise CreativeOperationError("stage must finish as ready, failed or cancelled")
        async with self.database.session() as session:
            operation = await self._owned_operation(session, tenant_id, operation_id)
            stage = await session.get(CreativeStageRunModel, stage_run_id)
            if stage is None or stage.operation_id != operation_id:
                raise CreativeOperationError("stage is outside operation")
            stage.status = status
            stage.error = error
            stage.finished_at = utc_now()
            operation.status = {
                CreativeStageStatus.READY: CreativeOperationStatus.SUCCEEDED,
                CreativeStageStatus.FAILED: CreativeOperationStatus.FAILED,
                CreativeStageStatus.CANCELLED: CreativeOperationStatus.CANCELLED,
            }[status]
            operation.completed_at = utc_now()
            await session.flush()
            return self._operation_view(operation)

    async def finish_operation_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        status: CreativeStageStatus,
        error: dict[str, object] | None = None,
    ) -> OperationView | None:
        if status not in {
            CreativeStageStatus.READY,
            CreativeStageStatus.FAILED,
            CreativeStageStatus.CANCELLED,
        }:
            raise CreativeOperationError("stage must finish as ready, failed or cancelled")
        async with self.database.session() as session:
            operation = (
                await session.scalars(
                    select(CreativeOperationModel).where(
                        CreativeOperationModel.tenant_id == tenant_id,
                        CreativeOperationModel.run_id == run_id,
                    )
                )
            ).one_or_none()
            if operation is None:
                return None
            stage = (
                await session.scalars(
                    select(CreativeStageRunModel)
                    .where(CreativeStageRunModel.operation_id == operation.id)
                    .order_by(
                        CreativeStageRunModel.attempt.desc(),
                        CreativeStageRunModel.created_at.desc(),
                    )
                )
            ).first()
            if stage is not None:
                stage.status = status
                stage.error = error
                stage.finished_at = utc_now()
            pending = list(
                await session.scalars(
                    select(CreativeDecisionRequestModel).where(
                        CreativeDecisionRequestModel.operation_id == operation.id,
                        CreativeDecisionRequestModel.status == DecisionRequestStatus.PENDING,
                    )
                )
            )
            if status == CreativeStageStatus.CANCELLED:
                for decision in pending:
                    decision.status = DecisionRequestStatus.CANCELLED
                    decision.decided_at = utc_now()
            operation.status = {
                CreativeStageStatus.READY: CreativeOperationStatus.SUCCEEDED,
                CreativeStageStatus.FAILED: CreativeOperationStatus.FAILED,
                CreativeStageStatus.CANCELLED: CreativeOperationStatus.CANCELLED,
            }[status]
            operation.completed_at = utc_now()
            await session.flush()
            return self._operation_view(operation)

    @staticmethod
    async def _owned_session(session: object, tenant_id: str, session_id: str):
        item = await session.get(CreativeSessionModel, session_id)
        if item is None or item.tenant_id != tenant_id:
            raise CreativeOperationError("creative session is outside tenant scope")
        return item

    @staticmethod
    async def _owned_operation(session: object, tenant_id: str, operation_id: str):
        item = await session.get(CreativeOperationModel, operation_id)
        if item is None or item.tenant_id != tenant_id:
            raise CreativeOperationError("operation is outside tenant scope")
        return item

    @staticmethod
    async def _validate_optional_refs(
        session: object,
        *,
        operation_id: str,
        artifact_ref_id: str | None,
        checkpoint_id: str | None,
    ) -> None:
        if artifact_ref_id is not None:
            artifact = await session.get(CreativeArtifactRefModel, artifact_ref_id)
            if artifact is None or artifact.operation_id != operation_id:
                raise CreativeOperationError("artifact is outside operation")
        if checkpoint_id is not None:
            checkpoint = await session.get(CreativeCheckpointModel, checkpoint_id)
            if checkpoint is None or checkpoint.operation_id != operation_id:
                raise CreativeOperationError("checkpoint is outside operation")

    @staticmethod
    def _operation_view(item: CreativeOperationModel) -> OperationView:
        return OperationView(
            id=item.id,
            session_id=item.session_id,
            run_id=item.run_id,
            command=item.command,
            domain=item.domain,
            stage=item.stage,
            status=item.status,
        )

    @staticmethod
    def _decision_view(item: CreativeDecisionRequestModel) -> DecisionView:
        return DecisionView(
            id=item.id,
            operation_id=item.operation_id,
            stage_run_id=item.stage_run_id,
            status=item.status,
            decision=item.decision,
            decided_at=item.decided_at,
        )
