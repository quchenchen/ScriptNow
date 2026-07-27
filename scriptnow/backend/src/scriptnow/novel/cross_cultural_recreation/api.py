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
from scriptnow.platform.agent_runtime import AgentRuntime
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel


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
) -> APIRouter:
    router = APIRouter(
        prefix="/cross-cultural-recreations",
        tags=["cross-cultural-recreation"],
    )
    service = CrossCulturalRecreationService(database)
    generator = CrossCulturalRecreationGenerator(database, AgentRuntime(database, settings))

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

    @router.post("/by-project/{project_id}/analyze-source")
    async def analyze_source(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
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
            )
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.SOURCE_STORY_MODEL,
                payloads=(payload,),
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
                adopt=True,
            )
            return _artifact(records[0])
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

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

    @router.post("/by-project/{project_id}/strategies")
    async def generate_strategies(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[dict[str, object]]:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
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
            )
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.RECREATION_STRATEGY,
                payloads=payloads,
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            return [_artifact(item) for item in records]
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

    @router.post("/by-project/{project_id}/pilots")
    async def generate_pilot(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
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
            )
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.PILOT,
                payloads=(payload,),
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            return _artifact(records[0])
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @router.post("/by-project/{project_id}/scale-plans")
    async def generate_scale_plan(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
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
            )
            records = await service.record_artifacts(
                recreation_id=record.id,
                kind=RecreationArtifactKind.SCALE_PLAN,
                payloads=(payload,),
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            return _artifact(records[0])
        except CrossCulturalRecreationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except RecreationGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

    @router.post("/by-project/{project_id}/work-packages/{work_package_key}/drafts")
    async def generate_production_unit(
        project_id: str,
        work_package_key: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        tenant_id = str(auth_context.tenant_id)
        try:
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
                return _production_unit(unit)
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
                )
                unit = await service.complete_production_unit(unit_id=unit.id, payload=payload)
            except RecreationGenerationError as error:
                await service.fail_production_unit(unit_id=unit.id, reason=str(error))
                raise
            return _production_unit(unit)
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
