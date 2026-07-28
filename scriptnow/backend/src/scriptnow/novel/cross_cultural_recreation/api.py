import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from scriptnow.novel.cross_cultural_recreation.domain import (
    CrossCulturalArtifactModel,
    RecreationArtifactKind,
    RecreationArtifactStatus,
    RecreationProductionUnitModel,
)
from scriptnow.novel.cross_cultural_recreation.generator import (
    CrossCulturalRecreationGenerator,
    RecreationGenerationError,
)
from scriptnow.novel.cross_cultural_recreation.service import (
    CrossCulturalRecreationError,
    CrossCulturalRecreationService,
)
from scriptnow.platform.active_runs import ActiveRunRegistry
from scriptnow.platform.agent_runtime import AgentRuntime
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.creative_operations import (
    CreativeOperationStore,
    coherent_run_status,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import CreativeStageStatus, ProjectModel, RunStatus
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType


class CreateRecreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    source_language: str = Field(min_length=2, max_length=24)
    target_language: str = Field(min_length=2, max_length=24)
    target_market: str = Field(min_length=2, max_length=160)
    target_audience: str = Field(min_length=2, max_length=240)
    distribution_context: str = Field(default="", max_length=160)


class TargetContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    genre_promise: str = Field(min_length=2)
    background_policy: str = Field(min_length=2)
    cultural_distance: str = Field(min_length=2)
    protected_elements: list[str] = Field(min_length=1)
    allowed_changes: list[str] = Field(default_factory=list)
    prohibited_changes: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1, max_length=120)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=120)
    feedback: str | None = None


class ManualRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    target_language_draft: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=120)


def _artifact(item: CrossCulturalArtifactModel) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": str(item.kind),
        "version": item.version,
        "ordinal": item.ordinal,
        "status": str(item.status),
        "payload": dict(item.payload),
        "feedback": item.feedback,
    }


def _production_unit(item: RecreationProductionUnitModel) -> dict[str, object]:
    return {
        "id": item.id,
        "scale_plan_artifact_id": item.scale_plan_artifact_id,
        "work_package_key": item.work_package_key,
        "version": item.version,
        "status": str(item.status),
        "pipeline_status": str(item.pipeline_status),
        "revision_kind": str(item.revision_kind),
        "source_unit_id": item.source_unit_id,
        "payload": dict(item.payload),
        "context_snapshot": dict(item.context_snapshot),
        "review_report": (dict(item.review_report) if item.review_report is not None else None),
        "failure_reason": item.failure_reason,
        "feedback": item.feedback,
    }


async def _state_payload(
    service: CrossCulturalRecreationService,
    *,
    tenant_id: str,
    project_id: str,
) -> dict[str, object]:
    record = await service.get(tenant_id=tenant_id, project_id=project_id)
    await service.sync_project_events(tenant_id=tenant_id, project_id=project_id)
    artifacts = await service.artifacts(recreation_id=record.id)
    production_units = await service.production_units(recreation_id=record.id)
    return {
        "id": record.id,
        "project_id": record.project_id,
        "source_language": record.source_language,
        "target_language": record.target_language,
        "target_market": record.target_market,
        "target_audience": record.target_audience,
        "distribution_context": record.distribution_context,
        "status": str(record.status),
        "artifacts": [_artifact(item) for item in artifacts],
        "production_units": [_production_unit(item) for item in production_units],
    }


def create_cross_cultural_recreation_router(
    database: Database,
    auth: AuthService,
    settings: Settings,
    active_runs: ActiveRunRegistry,
) -> APIRouter:
    router = APIRouter(
        prefix="/cross-cultural-recreations",
        tags=["cross-cultural-recreation"],
    )
    service = CrossCulturalRecreationService(database)
    generator = CrossCulturalRecreationGenerator(database, AgentRuntime(database, settings))
    operations = CreativeOperationStore(database)
    run_events = PersistentRunEventLog(database)

    async def context(
        access_token: str | None,
        csrf_token: str | None = None,
        *,
        write: bool,
    ):
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            if write:
                if csrf_token is None:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
                return await auth.authorize_action(access_token, csrf_token)
            return await auth.validate_access(access_token)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_recreation(
        body: CreateRecreationRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            record = await service.create(
                tenant_id=str(auth_context.tenant_id),
                project_id=body.project_id,
                source_language=body.source_language,
                target_language=body.target_language,
                target_market=body.target_market,
                target_audience=body.target_audience,
                distribution_context=body.distribution_context,
            )
            return await _state_payload(
                service,
                tenant_id=str(auth_context.tenant_id),
                project_id=record.project_id,
            )
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/by-project/{project_id}")
    async def state(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, write=False)
        try:
            return await _state_payload(
                service,
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
            )
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    async def _analyze_source_work(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        run_id: str | None = None,
    ) -> CrossCulturalArtifactModel:
        record = await service.get(tenant_id=tenant_id, project_id=project_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
        if project is None:
            raise CrossCulturalRecreationError("项目不存在")
        payload = await generator.analyze_source(
            tenant_id=tenant_id,
            project=project,
            idempotency_key=body.idempotency_key,
            target_contract={
                "target_language": record.target_language,
                "target_market": record.target_market,
                "target_audience": record.target_audience,
                "distribution_context": record.distribution_context,
            },
            run_id=run_id,
        )
        records = await service.record_artifacts(
            recreation_id=record.id,
            kind=RecreationArtifactKind.SOURCE_STORY_MODEL,
            payloads=(payload,),
            idempotency_key=body.idempotency_key,
            feedback=body.feedback,
            adopt=True,
        )
        return records[0]

    async def _background_analyze_source(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        run_id: str,
        operation_id: str,
        stage_run_id: str,
        input_digest: str,
    ) -> None:
        coordinator = RunCoordinator(database)
        try:
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.RUNNING,
            )
            artifact = await _analyze_source_work(
                tenant_id=tenant_id,
                project_id=project_id,
                body=body,
                run_id=run_id,
            )
            artifact_ref_id = await operations.register_artifact(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                domain="novel_recreation",
                artifact_type=RecreationArtifactKind.SOURCE_STORY_MODEL.value,
                artifact_id=artifact.id,
                revision=artifact.version,
                status=str(artifact.status),
                schema_version=1,
                input_digest=input_digest,
                dependency_versions={"project_id": project_id},
                provenance={"source": "agent", "run_id": run_id},
            )
            await operations.save_checkpoint(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                checkpoint_key=f"novel_recreation.source.analyze:{artifact.id}",
                state_format="json",
                state_payload=json.dumps(
                    {
                        "artifact_id": artifact.id,
                        "artifact_ref_id": artifact_ref_id,
                        "artifact_kind": str(artifact.kind),
                        "version": artifact.version,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode(),
                resume_metadata={"next_action": "confirm_target_contract"},
                is_complete=True,
            )
            await operations.finish_stage(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                status=CreativeStageStatus.READY,
            )
            await run_events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="recreation-source-model-persisted",
                type=RunEventType.TERMINAL,
                payload={
                    "block": "system",
                    "phase": "end",
                    "title": "源作品分析已保存",
                    "artifact_id": artifact.id,
                    "runtime": "agentscope",
                },
                correlation_id=run_id,
            )
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.SUCCEEDED,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await coordinator.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.CANCELLED,
                )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.CANCELLED,
                )
            raise
        except Exception as error:
            with suppress(Exception):
                current = await coordinator.status(tenant_id=tenant_id, run_id=run_id)
                if current is not None and current.status in {
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                    RunStatus.WAITING,
                }:
                    await coordinator.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code="recreation_source_analysis_failed",
                    )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.FAILED,
                    error={
                        "code": "recreation_source_analysis_failed",
                        "message": str(error),
                    },
                )
            with suppress(Exception):
                await service.record_generation_failure(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    stage="source_analysis",
                    run_id=run_id,
                    message=str(error),
                )

    @router.post("/by-project/{project_id}/analyze-source")
    async def analyze_source(
        project_id: str,
        body: GenerateRequest,
        background: Annotated[bool, Query()] = False,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
            if not background:
                artifact = await _analyze_source_work(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    body=body,
                )
                return _artifact(artifact)

            await service.get(tenant_id=tenant_id, project_id=project_id)
            coordinator = RunCoordinator(database)
            run = await coordinator.enqueue(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=body.idempotency_key,
            )
            session_id = await operations.get_or_open_session(
                tenant_id=tenant_id,
                project_id=project_id,
                active_domain="novel_recreation",
            )
            turn_id = await operations.append_turn(
                tenant_id=tenant_id,
                session_id=session_id,
                actor={"type": "user"},
                input={
                    "command": "novel_recreation.source.analyze",
                    "feedback": body.feedback,
                },
            )
            input_digest = hashlib.sha256(
                json.dumps(
                    {
                        "project_id": project_id,
                        "feedback": body.feedback,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            operation = await operations.enqueue_operation(
                tenant_id=tenant_id,
                session_id=session_id,
                turn_id=turn_id,
                run_id=run.id,
                command="novel_recreation.source.analyze",
                domain="novel_recreation",
                stage="source_analysis",
                idempotency_key=body.idempotency_key,
                policy_snapshot={"delivery": "background", "adoption": "automatic"},
            )
            stage_run_id = await operations.start_stage(
                tenant_id=tenant_id,
                operation_id=operation.id,
                stage_key="source_analysis",
                attempt=1,
                input_digest=input_digest,
            )
            task = asyncio.create_task(
                _background_analyze_source(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    body=body,
                    run_id=run.id,
                    operation_id=operation.id,
                    stage_run_id=stage_run_id,
                    input_digest=input_digest,
                )
            )
            active_runs.track(run.id, task)
            return {
                "status": str(run.status),
                "run_id": run.id,
                "operation_id": operation.id,
                "creative_session_id": session_id,
            }
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @router.get("/by-project/{project_id}/runs/{run_id}")
    async def recreation_run(
        project_id: str,
        run_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, write=False)
        run = await RunCoordinator(database).status(
            tenant_id=str(auth_context.tenant_id),
            run_id=run_id,
        )
        if run is None or run.project_id != project_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
        operation = await operations.operation_for_run(
            tenant_id=str(auth_context.tenant_id),
            run_id=run_id,
        )
        return {
            "run_id": run.id,
            "status": coherent_run_status(
                run.status, operation.status if operation else None
            ),
            "error_code": run.error_code,
            "operation_id": operation.id if operation else None,
            "creative_session_id": operation.session_id if operation else None,
            "operation_status": operation.status if operation else None,
            "stage": operation.stage if operation else None,
        }

    @router.post("/by-project/{project_id}/target-contract")
    async def save_target_contract(
        project_id: str,
        body: TargetContractRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            record = await service.get(tenant_id=str(auth_context.tenant_id), project_id=project_id)
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.TARGET_STORY_CONTRACT,
                payloads=(body.model_dump(exclude={"idempotency_key"}),),
                idempotency_key=body.idempotency_key,
                adopt=True,
            )
            return _artifact(records[0])
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    async def _generate_strategies_work(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        run_id: str | None = None,
    ) -> tuple[CrossCulturalArtifactModel, ...]:
        record = await service.get(tenant_id=tenant_id, project_id=project_id)
        artifacts = await service.artifacts(recreation_id=record.id)
        adopted = {
            str(item.kind): dict(item.payload)
            for item in artifacts
            if str(item.status) == RecreationArtifactStatus.ADOPTED
        }
        source_model = adopted.get(RecreationArtifactKind.SOURCE_STORY_MODEL.value)
        target_contract = adopted.get(RecreationArtifactKind.TARGET_STORY_CONTRACT.value)
        if source_model is None or target_contract is None:
            raise CrossCulturalRecreationError("请先完成源作品分析并确认目标故事契约")
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
        if project is None:
            raise CrossCulturalRecreationError("项目不存在")
        payloads = await generator.generate_strategies(
            tenant_id=tenant_id,
            project=project,
            idempotency_key=body.idempotency_key,
            source_model=source_model,
            target_contract={
                **target_contract,
                "target_language": record.target_language,
                "target_market": record.target_market,
                "target_audience": record.target_audience,
                "distribution_context": record.distribution_context,
            },
            feedback=body.feedback,
            run_id=run_id,
        )
        return await service.record_artifacts(
            recreation_id=record.id,
            kind=RecreationArtifactKind.RECREATION_STRATEGY,
            payloads=payloads,
            idempotency_key=body.idempotency_key,
            feedback=body.feedback,
        )

    async def _background_generate_strategies(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        run_id: str,
        operation_id: str,
        stage_run_id: str,
        input_digest: str,
    ) -> None:
        coordinator = RunCoordinator(database)
        try:
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.RUNNING,
            )
            artifacts = await _generate_strategies_work(
                tenant_id=tenant_id,
                project_id=project_id,
                body=body,
                run_id=run_id,
            )
            artifact_refs: list[dict[str, object]] = []
            for artifact in artifacts:
                artifact_ref_id = await operations.register_artifact(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    domain="novel_recreation",
                    artifact_type=RecreationArtifactKind.RECREATION_STRATEGY.value,
                    artifact_id=artifact.id,
                    revision=artifact.version,
                    status=str(artifact.status),
                    schema_version=1,
                    input_digest=input_digest,
                    dependency_versions={"project_id": project_id},
                    provenance={"source": "agent", "run_id": run_id},
                )
                artifact_refs.append(
                    {
                        "artifact_id": artifact.id,
                        "artifact_ref_id": artifact_ref_id,
                        "version": artifact.version,
                    }
                )
            await operations.save_checkpoint(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                checkpoint_key=f"novel_recreation.strategy.generate:{run_id}",
                state_format="json",
                state_payload=json.dumps(
                    {
                        "artifact_kind": RecreationArtifactKind.RECREATION_STRATEGY.value,
                        "candidates": artifact_refs,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode(),
                resume_metadata={"next_action": "adopt_recreation_strategy"},
                is_complete=True,
            )
            await operations.finish_stage(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                status=CreativeStageStatus.READY,
            )
            await run_events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="recreation-strategy-candidates-persisted",
                type=RunEventType.TERMINAL,
                payload={
                    "block": "system",
                    "phase": "end",
                    "title": "归化策略候选已保存",
                    "artifact_ids": [item.id for item in artifacts],
                    "candidate_count": len(artifacts),
                    "runtime": "agentscope",
                },
                correlation_id=run_id,
            )
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.SUCCEEDED,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await coordinator.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.CANCELLED,
                )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.CANCELLED,
                )
            raise
        except Exception as error:
            with suppress(Exception):
                current = await coordinator.status(tenant_id=tenant_id, run_id=run_id)
                if current is not None and current.status in {
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                    RunStatus.WAITING,
                }:
                    await coordinator.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code="recreation_strategy_generation_failed",
                    )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.FAILED,
                    error={
                        "code": "recreation_strategy_generation_failed",
                        "message": str(error),
                    },
                )
            with suppress(Exception):
                await service.record_generation_failure(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    stage="strategy",
                    run_id=run_id,
                    message=str(error),
                )

    @router.post("/by-project/{project_id}/strategies")
    async def generate_strategies(
        project_id: str,
        body: GenerateRequest,
        background: Annotated[bool, Query()] = False,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> object:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
            if not background:
                records = await _generate_strategies_work(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    body=body,
                )
                return [_artifact(item) for item in records]

            await service.get(tenant_id=tenant_id, project_id=project_id)
            coordinator = RunCoordinator(database)
            run = await coordinator.enqueue(
                tenant_id=tenant_id,
                idempotency_key=body.idempotency_key,
                project_id=project_id,
            )
            session_id = await operations.get_or_open_session(
                tenant_id=tenant_id,
                project_id=project_id,
                active_domain="novel_recreation",
            )
            turn_id = await operations.append_turn(
                tenant_id=tenant_id,
                session_id=session_id,
                actor={"type": "user"},
                input={
                    "command": "novel_recreation.strategy.generate",
                    "feedback": body.feedback,
                },
            )
            input_digest = hashlib.sha256(
                json.dumps(
                    {
                        "project_id": project_id,
                        "feedback": body.feedback,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            operation = await operations.enqueue_operation(
                tenant_id=tenant_id,
                session_id=session_id,
                turn_id=turn_id,
                run_id=run.id,
                command="novel_recreation.strategy.generate",
                domain="novel_recreation",
                stage="strategy",
                idempotency_key=body.idempotency_key,
                policy_snapshot={"delivery": "background", "adoption": "manual"},
            )
            stage_run_id = await operations.start_stage(
                tenant_id=tenant_id,
                operation_id=operation.id,
                stage_key="strategy",
                attempt=1,
                input_digest=input_digest,
            )
            task = asyncio.create_task(
                _background_generate_strategies(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    body=body,
                    run_id=run.id,
                    operation_id=operation.id,
                    stage_run_id=stage_run_id,
                    input_digest=input_digest,
                )
            )
            active_runs.track(run.id, task)
            return {
                "status": str(run.status),
                "run_id": run.id,
                "operation_id": operation.id,
                "creative_session_id": session_id,
            }
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @router.post("/by-project/{project_id}/artifacts/{artifact_id}/adopt")
    async def adopt_artifact(
        project_id: str,
        artifact_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.adopt(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                artifact_id=artifact_id,
            )
            return _artifact(item)
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    async def _run_artifact_generation(
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        operation_id: str,
        stage_run_id: str,
        input_digest: str,
        artifact_kind: RecreationArtifactKind,
        stage: str,
        failure_code: str,
        next_action: str,
        work: Callable[[str], Awaitable[CrossCulturalArtifactModel]],
    ) -> None:
        coordinator = RunCoordinator(database)
        try:
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.RUNNING,
            )
            artifact = await work(run_id)
            artifact_ref_id = await operations.register_artifact(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                domain="novel_recreation",
                artifact_type=artifact_kind.value,
                artifact_id=artifact.id,
                revision=artifact.version,
                status=str(artifact.status),
                schema_version=1,
                input_digest=input_digest,
                dependency_versions={"project_id": project_id},
                provenance={"source": "agent", "run_id": run_id},
            )
            await operations.save_checkpoint(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                checkpoint_key=f"novel_recreation.{stage}:{artifact.id}",
                state_format="json",
                state_payload=json.dumps(
                    {
                        "artifact_kind": artifact_kind.value,
                        "artifact_id": artifact.id,
                        "artifact_ref_id": artifact_ref_id,
                        "version": artifact.version,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode(),
                resume_metadata={"next_action": next_action},
                is_complete=True,
            )
            await operations.finish_stage(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                status=CreativeStageStatus.READY,
            )
            await run_events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key=f"recreation-{stage}-persisted",
                type=RunEventType.TERMINAL,
                payload={
                    "block": "system",
                    "phase": "end",
                    "artifact_id": artifact.id,
                    "artifact_kind": artifact_kind.value,
                    "runtime": "agentscope",
                },
                correlation_id=run_id,
            )
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.SUCCEEDED,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await coordinator.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.CANCELLED,
                )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.CANCELLED,
                )
            raise
        except Exception as error:
            with suppress(Exception):
                current = await coordinator.status(tenant_id=tenant_id, run_id=run_id)
                if current is not None and current.status in {
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                    RunStatus.WAITING,
                }:
                    await coordinator.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code=failure_code,
                    )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.FAILED,
                    error={"code": failure_code, "message": str(error)},
                )
            with suppress(Exception):
                await service.record_generation_failure(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    stage=stage,
                    run_id=run_id,
                    message=str(error),
                )

    async def _enqueue_artifact_generation(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        command: str,
        stage: str,
        artifact_kind: RecreationArtifactKind,
        failure_code: str,
        next_action: str,
        work: Callable[[str], Awaitable[CrossCulturalArtifactModel]],
    ) -> dict[str, object]:
        await service.get(tenant_id=tenant_id, project_id=project_id)
        coordinator = RunCoordinator(database)
        run = await coordinator.enqueue(
            tenant_id=tenant_id,
            idempotency_key=body.idempotency_key,
            project_id=project_id,
        )
        session_id = await operations.get_or_open_session(
            tenant_id=tenant_id,
            project_id=project_id,
            active_domain="novel_recreation",
        )
        turn_id = await operations.append_turn(
            tenant_id=tenant_id,
            session_id=session_id,
            actor={"type": "user"},
            input={"command": command, "feedback": body.feedback},
        )
        input_digest = hashlib.sha256(
            json.dumps(
                {"project_id": project_id, "feedback": body.feedback, "stage": stage},
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        operation = await operations.enqueue_operation(
            tenant_id=tenant_id,
            session_id=session_id,
            turn_id=turn_id,
            run_id=run.id,
            command=command,
            domain="novel_recreation",
            stage=stage,
            idempotency_key=body.idempotency_key,
            policy_snapshot={"delivery": "background", "adoption": "manual"},
        )
        stage_run_id = await operations.start_stage(
            tenant_id=tenant_id,
            operation_id=operation.id,
            stage_key=stage,
            attempt=1,
            input_digest=input_digest,
        )
        task = asyncio.create_task(
            _run_artifact_generation(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run.id,
                operation_id=operation.id,
                stage_run_id=stage_run_id,
                input_digest=input_digest,
                artifact_kind=artifact_kind,
                stage=stage,
                failure_code=failure_code,
                next_action=next_action,
                work=work,
            )
        )
        active_runs.track(run.id, task)
        return {
            "status": str(run.status),
            "run_id": run.id,
            "operation_id": operation.id,
            "creative_session_id": session_id,
        }

    async def _generate_pilot_work(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        run_id: str | None = None,
    ) -> CrossCulturalArtifactModel:
            record = await service.get(tenant_id=tenant_id, project_id=project_id)
            artifacts = await service.artifacts(recreation_id=record.id)
            adopted = {
                str(item.kind): dict(item.payload)
                for item in artifacts
                if str(item.status) == RecreationArtifactStatus.ADOPTED
            }
            source_model = adopted.get(RecreationArtifactKind.SOURCE_STORY_MODEL.value)
            target_contract = adopted.get(RecreationArtifactKind.TARGET_STORY_CONTRACT.value)
            strategy = adopted.get(RecreationArtifactKind.RECREATION_STRATEGY.value)
            if source_model is None or target_contract is None or strategy is None:
                raise CrossCulturalRecreationError("请先确认源作品模型、目标故事契约和归化策略")
            async with database.session() as session:
                project = await session.get(ProjectModel, project_id)
            if project is None:
                raise CrossCulturalRecreationError("项目不存在")
            payload = await generator.generate_pilot(
                tenant_id=tenant_id,
                project=project,
                idempotency_key=body.idempotency_key,
                source_model=source_model,
                target_contract={
                    **target_contract,
                    "target_language": record.target_language,
                    "target_market": record.target_market,
                    "target_audience": record.target_audience,
                    "distribution_context": record.distribution_context,
                },
                strategy=strategy,
                feedback=body.feedback,
                run_id=run_id,
            )
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.PILOT,
                payloads=(payload,),
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            return records[0]

    @router.post("/by-project/{project_id}/pilots")
    async def generate_pilot(
        project_id: str,
        body: GenerateRequest,
        background: Annotated[bool, Query()] = False,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> object:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
            if not background:
                return _artifact(
                    await _generate_pilot_work(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        body=body,
                    )
                )

            async def work(run_id: str) -> CrossCulturalArtifactModel:
                return await _generate_pilot_work(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    body=body,
                    run_id=run_id,
                )

            return await _enqueue_artifact_generation(
                tenant_id=tenant_id,
                project_id=project_id,
                body=body,
                command="novel_recreation.pilot.generate",
                stage="pilot",
                artifact_kind=RecreationArtifactKind.PILOT,
                failure_code="recreation_pilot_generation_failed",
                next_action="adopt_recreation_pilot",
                work=work,
            )
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    async def _generate_scale_plan_work(
        *,
        tenant_id: str,
        project_id: str,
        body: GenerateRequest,
        run_id: str | None = None,
    ) -> CrossCulturalArtifactModel:
            record = await service.get(tenant_id=tenant_id, project_id=project_id)
            artifacts = await service.artifacts(recreation_id=record.id)
            adopted = {
                str(item.kind): dict(item.payload)
                for item in artifacts
                if str(item.status) == RecreationArtifactStatus.ADOPTED
            }
            source_model = adopted.get(RecreationArtifactKind.SOURCE_STORY_MODEL.value)
            target_contract = adopted.get(RecreationArtifactKind.TARGET_STORY_CONTRACT.value)
            strategy = adopted.get(RecreationArtifactKind.RECREATION_STRATEGY.value)
            pilot = adopted.get(RecreationArtifactKind.PILOT.value)
            if source_model is None or target_contract is None or strategy is None or pilot is None:
                raise CrossCulturalRecreationError(
                    "请先确认源作品模型、目标故事契约、归化策略和代表性试写"
                )
            async with database.session() as session:
                project = await session.get(ProjectModel, project_id)
            if project is None:
                raise CrossCulturalRecreationError("项目不存在")
            payload = await generator.generate_scale_plan(
                tenant_id=tenant_id,
                project=project,
                idempotency_key=body.idempotency_key,
                source_model=source_model,
                target_contract={
                    **target_contract,
                    "target_language": record.target_language,
                    "target_market": record.target_market,
                    "target_audience": record.target_audience,
                    "distribution_context": record.distribution_context,
                },
                strategy=strategy,
                pilot=pilot,
                feedback=body.feedback,
                run_id=run_id,
            )
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.SCALE_PLAN,
                payloads=(payload,),
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            return records[0]

    @router.post("/by-project/{project_id}/scale-plans")
    async def generate_scale_plan(
        project_id: str,
        body: GenerateRequest,
        background: Annotated[bool, Query()] = False,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> object:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
            if not background:
                return _artifact(
                    await _generate_scale_plan_work(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        body=body,
                    )
                )

            async def work(run_id: str) -> CrossCulturalArtifactModel:
                return await _generate_scale_plan_work(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    body=body,
                    run_id=run_id,
                )

            return await _enqueue_artifact_generation(
                tenant_id=tenant_id,
                project_id=project_id,
                body=body,
                command="novel_recreation.scale_plan.generate",
                stage="scale_plan",
                artifact_kind=RecreationArtifactKind.SCALE_PLAN,
                failure_code="recreation_scale_plan_generation_failed",
                next_action="adopt_recreation_scale_plan",
                work=work,
            )
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    async def _generate_production_unit_work(
        *,
        tenant_id: str,
        project_id: str,
        work_package_key: str,
        body: GenerateRequest,
        run_id: str | None = None,
    ) -> RecreationProductionUnitModel:
            record = await service.get(tenant_id=tenant_id, project_id=project_id)
            artifacts = await service.artifacts(recreation_id=record.id)
            adopted_artifacts = {
                str(item.kind): item
                for item in artifacts
                if str(item.status) == RecreationArtifactStatus.ADOPTED
            }
            required_kinds = (
                RecreationArtifactKind.SOURCE_STORY_MODEL,
                RecreationArtifactKind.TARGET_STORY_CONTRACT,
                RecreationArtifactKind.RECREATION_STRATEGY,
                RecreationArtifactKind.PILOT,
                RecreationArtifactKind.SCALE_PLAN,
            )
            if any(kind.value not in adopted_artifacts for kind in required_kinds):
                raise CrossCulturalRecreationError(
                    "请先确认源作品模型、目标故事契约、归化策略、代表性试写和整书扩展方案"
                )
            scale_plan_artifact = adopted_artifacts[RecreationArtifactKind.SCALE_PLAN.value]
            scale_plan = dict(scale_plan_artifact.payload)
            work_packages = [
                item
                for item in scale_plan.get("work_packages", [])
                if isinstance(item, dict) and item.get("order") is not None
            ]
            work_package = next(
                (item for item in work_packages if str(item.get("order")) == work_package_key),
                None,
            )
            if work_package is None:
                raise CrossCulturalRecreationError("整书方案中不存在该工作包")
            current_index = work_packages.index(work_package)
            earlier_keys = {str(item["order"]) for item in work_packages[:current_index]}
            units = await service.production_units(recreation_id=record.id)
            adopted_units = [
                dict(item.payload)
                for item in units
                if item.scale_plan_artifact_id == scale_plan_artifact.id
                and str(item.status) == RecreationArtifactStatus.ADOPTED
                and item.work_package_key in earlier_keys
            ]
            async with database.session() as session:
                project = await session.get(ProjectModel, project_id)
            if project is None:
                raise CrossCulturalRecreationError("项目不存在")
            target_contract = dict(
                adopted_artifacts[RecreationArtifactKind.TARGET_STORY_CONTRACT.value].payload
            )
            context_snapshot = {
                "scale_plan_artifact_id": scale_plan_artifact.id,
                "scale_plan_version": scale_plan_artifact.version,
                "work_package": work_package,
                "earlier_adopted_units": [
                    {
                        "work_package_key": item.work_package_key,
                        "version": item.version,
                        "unit_id": item.id,
                    }
                    for item in units
                    if item.scale_plan_artifact_id == scale_plan_artifact.id
                    and str(item.status) == RecreationArtifactStatus.ADOPTED
                    and item.work_package_key in earlier_keys
                ],
                "target_contract_artifact_id": adopted_artifacts[
                    RecreationArtifactKind.TARGET_STORY_CONTRACT.value
                ].id,
            }
            unit = await service.start_production_unit(
                recreation_id=record.id,
                scale_plan_artifact_id=scale_plan_artifact.id,
                work_package_key=work_package_key,
                idempotency_key=body.idempotency_key,
                context_snapshot=context_snapshot,
                feedback=body.feedback,
            )
            if dict(unit.payload):
                return unit
            try:
                payload = await generator.generate_production_unit(
                    tenant_id=tenant_id,
                    project=project,
                    idempotency_key=body.idempotency_key,
                    source_model=dict(
                        adopted_artifacts[RecreationArtifactKind.SOURCE_STORY_MODEL.value].payload
                    ),
                    target_contract={
                        **target_contract,
                        "target_language": record.target_language,
                        "target_market": record.target_market,
                        "target_audience": record.target_audience,
                        "distribution_context": record.distribution_context,
                    },
                    strategy=dict(
                        adopted_artifacts[RecreationArtifactKind.RECREATION_STRATEGY.value].payload
                    ),
                    pilot=dict(adopted_artifacts[RecreationArtifactKind.PILOT.value].payload),
                    scale_plan=scale_plan,
                    work_package=work_package,
                    adopted_units=adopted_units,
                    feedback=body.feedback,
                    run_id=run_id,
                )
                unit = await service.complete_production_unit(unit_id=unit.id, payload=payload)
            except Exception as error:
                await service.fail_production_unit(unit_id=unit.id, reason=str(error))
                raise
            return unit

    async def _background_generate_production_unit(
        *,
        tenant_id: str,
        project_id: str,
        work_package_key: str,
        body: GenerateRequest,
        run_id: str,
        operation_id: str,
        stage_run_id: str,
        input_digest: str,
    ) -> None:
        coordinator = RunCoordinator(database)
        try:
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.RUNNING,
            )
            unit = await _generate_production_unit_work(
                tenant_id=tenant_id,
                project_id=project_id,
                work_package_key=work_package_key,
                body=body,
                run_id=run_id,
            )
            artifact_ref_id = await operations.register_artifact(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                domain="novel_recreation",
                artifact_type="production_unit",
                artifact_id=unit.id,
                revision=unit.version,
                status=str(unit.status),
                schema_version=1,
                input_digest=input_digest,
                dependency_versions={
                    "project_id": project_id,
                    "scale_plan_artifact_id": unit.scale_plan_artifact_id,
                },
                provenance={"source": "agent", "run_id": run_id},
            )
            await operations.save_checkpoint(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                checkpoint_key=f"novel_recreation.production:{unit.id}",
                state_format="json",
                state_payload=json.dumps(
                    {
                        "production_unit_id": unit.id,
                        "artifact_ref_id": artifact_ref_id,
                        "work_package_key": unit.work_package_key,
                        "version": unit.version,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode(),
                resume_metadata={"next_action": "review_recreation_production_unit"},
                is_complete=True,
            )
            await operations.finish_stage(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                status=CreativeStageStatus.READY,
            )
            await run_events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="recreation-production-unit-persisted",
                type=RunEventType.TERMINAL,
                payload={
                    "block": "system",
                    "phase": "end",
                    "production_unit_id": unit.id,
                    "work_package_key": unit.work_package_key,
                    "runtime": "agentscope",
                },
                correlation_id=run_id,
            )
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.SUCCEEDED,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await coordinator.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.CANCELLED,
                )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.CANCELLED,
                )
            raise
        except Exception as error:
            with suppress(Exception):
                current = await coordinator.status(tenant_id=tenant_id, run_id=run_id)
                if current is not None and current.status in {
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                    RunStatus.WAITING,
                }:
                    await coordinator.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code="recreation_production_generation_failed",
                    )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.FAILED,
                    error={
                        "code": "recreation_production_generation_failed",
                        "message": str(error),
                    },
                )
            with suppress(Exception):
                await service.record_generation_failure(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    stage="production",
                    run_id=run_id,
                    message=str(error),
                )

    @router.post("/by-project/{project_id}/work-packages/{work_package_key}/drafts")
    async def generate_production_unit(
        project_id: str,
        work_package_key: str,
        body: GenerateRequest,
        background: Annotated[bool, Query()] = False,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> object:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
            if not background:
                return _production_unit(
                    await _generate_production_unit_work(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        work_package_key=work_package_key,
                        body=body,
                    )
                )

            await service.get(tenant_id=tenant_id, project_id=project_id)
            coordinator = RunCoordinator(database)
            run = await coordinator.enqueue(
                tenant_id=tenant_id,
                idempotency_key=body.idempotency_key,
                project_id=project_id,
            )
            session_id = await operations.get_or_open_session(
                tenant_id=tenant_id,
                project_id=project_id,
                active_domain="novel_recreation",
            )
            turn_id = await operations.append_turn(
                tenant_id=tenant_id,
                session_id=session_id,
                actor={"type": "user"},
                input={
                    "command": "novel_recreation.production.generate",
                    "work_package_key": work_package_key,
                    "feedback": body.feedback,
                },
            )
            input_digest = hashlib.sha256(
                json.dumps(
                    {
                        "project_id": project_id,
                        "work_package_key": work_package_key,
                        "feedback": body.feedback,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            operation = await operations.enqueue_operation(
                tenant_id=tenant_id,
                session_id=session_id,
                turn_id=turn_id,
                run_id=run.id,
                command="novel_recreation.production.generate",
                domain="novel_recreation",
                stage="production",
                idempotency_key=body.idempotency_key,
                policy_snapshot={"delivery": "background", "adoption": "manual"},
            )
            stage_run_id = await operations.start_stage(
                tenant_id=tenant_id,
                operation_id=operation.id,
                stage_key=f"production:{work_package_key}",
                attempt=1,
                input_digest=input_digest,
            )
            task = asyncio.create_task(
                _background_generate_production_unit(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    work_package_key=work_package_key,
                    body=body,
                    run_id=run.id,
                    operation_id=operation.id,
                    stage_run_id=stage_run_id,
                    input_digest=input_digest,
                )
            )
            active_runs.track(run.id, task)
            return {
                "status": str(run.status),
                "run_id": run.id,
                "operation_id": operation.id,
                "creative_session_id": session_id,
            }
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @router.post("/by-project/{project_id}/production-units/{unit_id}/review")
    async def review_production_unit(
        project_id: str,
        unit_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            unit = await service.review_production_unit(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                unit_id=unit_id,
            )
            return _production_unit(unit)
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post(
        "/by-project/{project_id}/production-units/{unit_id}/revisions",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_production_unit(
        project_id: str,
        unit_id: str,
        body: ManualRevisionRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            unit = await service.revise_production_unit(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                unit_id=unit_id,
                title=body.title,
                draft=body.target_language_draft,
                idempotency_key=body.idempotency_key,
            )
            return _production_unit(unit)
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/by-project/{project_id}/production-units/{unit_id}/adopt")
    async def adopt_production_unit(
        project_id: str,
        unit_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            unit = await service.adopt_production_unit(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                unit_id=unit_id,
            )
            return _production_unit(unit)
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/by-project/{project_id}/manuscript")
    async def assembled_manuscript(
        project_id: str,
        work_package_keys: Annotated[list[str] | None, Query()] = None,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, write=False)
        try:
            record = await service.get(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
            )
            artifacts = await service.artifacts(recreation_id=record.id)
            scale_plan = next(
                (
                    item
                    for item in artifacts
                    if str(item.kind) == RecreationArtifactKind.SCALE_PLAN
                    and str(item.status) == RecreationArtifactStatus.ADOPTED
                ),
                None,
            )
            if scale_plan is None:
                raise CrossCulturalRecreationError("请先确认整书扩展方案")
            package_keys = [
                str(item["order"])
                for item in scale_plan.payload.get("work_packages", [])
                if isinstance(item, dict) and item.get("order") is not None
            ]
            units = await service.production_units(recreation_id=record.id)
            adopted_by_key = {
                item.work_package_key: item
                for item in units
                if item.scale_plan_artifact_id == scale_plan.id
                and str(item.status) == RecreationArtifactStatus.ADOPTED
            }
            requested_keys = list(dict.fromkeys(work_package_keys or package_keys))
            unknown = [key for key in requested_keys if key not in package_keys]
            if unknown:
                raise CrossCulturalRecreationError("所选章节不在已确认的整书蓝图中")
            missing = [key for key in requested_keys if key not in adopted_by_key]
            if not requested_keys:
                raise CrossCulturalRecreationError("请至少选择一个章节")
            if missing:
                raise CrossCulturalRecreationError("所选章节中仍有尚未确认的稿件")
            ordered_keys = [key for key in package_keys if key in requested_keys]
            sections = [
                {
                    "work_package_key": key,
                    "version": adopted_by_key[key].version,
                    "title": str(adopted_by_key[key].payload.get("title", "")),
                    "content": str(adopted_by_key[key].payload.get("target_language_draft", "")),
                }
                for key in ordered_keys
            ]
            return {
                "project_id": project_id,
                "target_language": record.target_language,
                "sections": sections,
                "content": "\n\n".join(section["content"] for section in sections),
            }
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return router
