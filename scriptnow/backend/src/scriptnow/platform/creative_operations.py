import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from scriptnow.platform.context_manifest import ContextManifestStore
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeArtifactRefModel,
    CreativeCheckpointModel,
    CreativeDecisionRequestModel,
    CreativeOperationModel,
    CreativeOperationStatus,
    CreativeResumptionModel,
    CreativeResumptionStatus,
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

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, slots=True)
class CheckpointView:
    id: str
    operation_id: str
    stage_run_id: str | None
    state_format: str
    state_payload: bytes
    resume_metadata: dict[str, object]
    is_complete: bool


@dataclass(frozen=True, slots=True)
class ResumptionView:
    id: str
    operation_id: str
    decision_request_id: str
    checkpoint_id: str
    idempotency_key: str
    status: str
    result: dict[str, object] | None
    error: dict[str, object] | None


class CreativeOperationStore:
    """Persist shared execution lineage without owning domain artifacts."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.context_manifests = ContextManifestStore()

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
        retrieval_manifest_id: str | None = None,
    ) -> OperationView:
        async with self.database.session() as session:
            creative_session = await self._owned_session(session, tenant_id, session_id)
            project = await session.get(ProjectModel, creative_session.project_id)
            if project is None or project.tenant_id != tenant_id:
                raise CreativeOperationError("creative project no longer exists")
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
            if context_manifest_id is None:
                try:
                    manifest = await self.context_manifests.build(
                        session,
                        tenant_id=tenant_id,
                        project=project,
                        session_id=session_id,
                        turn_id=turn_id,
                        domain=domain,
                        stage=stage,
                        policy_snapshot=policy_snapshot,
                        retrieval_manifest_id=retrieval_manifest_id,
                    )
                except ValueError as error:
                    raise CreativeOperationError(str(error)) from error
                context_manifest_id = manifest.id
            else:
                try:
                    manifest_view = await self.context_manifests.load(
                        session,
                        tenant_id=tenant_id,
                        manifest_id=context_manifest_id,
                    )
                except ValueError as error:
                    raise CreativeOperationError(str(error)) from error
                manifest_project = manifest_view.content.get("project")
                if (
                    not isinstance(manifest_project, dict)
                    or manifest_project.get("id") != creative_session.project_id
                ):
                    raise CreativeOperationError(
                        "context manifest is outside creative project"
                    )
                if (
                    retrieval_manifest_id is not None
                    and manifest_view.retrieval_manifest_id != retrieval_manifest_id
                ):
                    raise CreativeOperationError(
                        "context manifest does not reference retrieval manifest"
                    )
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

    async def checkpoint_for_decision(
        self,
        *,
        tenant_id: str,
        decision_id: str,
    ) -> CheckpointView:
        async with self.database.session() as session:
            decision = await session.get(CreativeDecisionRequestModel, decision_id)
            if decision is None:
                raise CreativeOperationError("decision does not exist")
            await self._owned_operation(session, tenant_id, decision.operation_id)
            if decision.checkpoint_id is None:
                raise CreativeOperationError("decision does not have a checkpoint")
            checkpoint = await session.get(CreativeCheckpointModel, decision.checkpoint_id)
            if (
                checkpoint is None
                or checkpoint.operation_id != decision.operation_id
                or not checkpoint.is_complete
            ):
                raise CreativeOperationError("decision checkpoint is not resumable")
            return self._checkpoint_view(checkpoint)

    async def claim_resumption(
        self,
        *,
        tenant_id: str,
        decision_id: str,
        idempotency_key: str,
        claimed_by: dict[str, object],
    ) -> ResumptionView:
        """Claim a resolved parked decision once before executing any tool side effect.

        A second request with the same key observes the original claim. A different
        key is rejected, preventing a second process from replaying the same tool call.
        """
        async with self.database.session() as session:
            decision = await session.get(CreativeDecisionRequestModel, decision_id)
            if decision is None:
                raise CreativeOperationError("decision does not exist")
            await self._owned_operation(session, tenant_id, decision.operation_id)
            if decision.status not in {
                DecisionRequestStatus.APPROVED,
                DecisionRequestStatus.REJECTED,
            }:
                raise CreativeOperationError("decision must be resolved before resumption")
            if decision.checkpoint_id is None:
                raise CreativeOperationError("decision does not have a checkpoint")
            checkpoint = await session.get(CreativeCheckpointModel, decision.checkpoint_id)
            if checkpoint is None or not checkpoint.is_complete:
                raise CreativeOperationError("decision checkpoint is not resumable")
            existing = (
                await session.scalars(
                    select(CreativeResumptionModel).where(
                        CreativeResumptionModel.decision_request_id == decision_id
                    )
                )
            ).one_or_none()
            if existing is not None:
                if (
                    existing.idempotency_key != idempotency_key
                    or existing.claimed_by != claimed_by
                ):
                    raise CreativeOperationError("decision resumption is already claimed")
                return self._resumption_view(existing)
            claim = CreativeResumptionModel(
                operation_id=decision.operation_id,
                decision_request_id=decision.id,
                checkpoint_id=checkpoint.id,
                idempotency_key=idempotency_key,
                claimed_by=claimed_by,
            )
            session.add(claim)
            await session.flush()
            return self._resumption_view(claim)

    async def finish_resumption(
        self,
        *,
        tenant_id: str,
        resumption_id: str,
        result: dict[str, object] | None = None,
        error: dict[str, object] | None = None,
    ) -> ResumptionView:
        if (result is None) == (error is None):
            raise CreativeOperationError("resumption requires exactly one result or error")
        async with self.database.session() as session:
            claim = await session.get(CreativeResumptionModel, resumption_id)
            if claim is None:
                raise CreativeOperationError("resumption does not exist")
            await self._owned_operation(session, tenant_id, claim.operation_id)
            target = (
                CreativeResumptionStatus.COMPLETED
                if result is not None
                else CreativeResumptionStatus.FAILED
            )
            if claim.status != CreativeResumptionStatus.CLAIMED:
                if claim.status == target and claim.result == result and claim.error == error:
                    return self._resumption_view(claim)
                raise CreativeOperationError("resumption has already finished")
            claim.status = target
            claim.result = result
            claim.error = error
            claim.completed_at = utc_now()
            await session.flush()
            return self._resumption_view(claim)

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
        if error is not None:
            logger.warning(
                "creative stage finished %s with error: %s",
                status,
                error,
            )
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

    @staticmethod
    def _checkpoint_view(item: CreativeCheckpointModel) -> CheckpointView:
        return CheckpointView(
            id=item.id,
            operation_id=item.operation_id,
            stage_run_id=item.stage_run_id,
            state_format=item.state_format,
            state_payload=item.state_payload,
            resume_metadata=dict(item.resume_metadata),
            is_complete=item.is_complete,
        )

    @staticmethod
    def _resumption_view(item: CreativeResumptionModel) -> ResumptionView:
        return ResumptionView(
            id=item.id,
            operation_id=item.operation_id,
            decision_request_id=item.decision_request_id,
            checkpoint_id=item.checkpoint_id,
            idempotency_key=item.idempotency_key,
            status=item.status,
            result=item.result,
            error=item.error,
        )
