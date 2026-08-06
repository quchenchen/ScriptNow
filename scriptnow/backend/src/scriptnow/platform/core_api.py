import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from scriptnow.platform.agent_factory import AgentFactory, RuntimeConfigError
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
from scriptnow.platform.audit import AuditService
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.billing import BillingError, BillingService, PaymentRequired
from scriptnow.platform.config import Settings
from scriptnow.platform.creative_setup import creative_genre_options
from scriptnow.platform.database import Database
from scriptnow.platform.error_utils import user_facing_exception_message
from scriptnow.platform.models import (
    AgentTemplateVersionModel,
    LanguageModelModel,
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    ProjectSource,
    ProjectWorkflow,
    ProviderModel,
    ProviderStatus,
    RunStatus,
    SourceDistillationModel,
    SourceEvidenceModel,
    SourceProfileModel,
    TenantAgentConfigModel,
    TenantModel,
    TierModel,
    TokenAccountModel,
    WorkspaceFileModel,
)
from scriptnow.platform.rag import RagService
from scriptnow.platform.run_coordinator import RunCoordinator, RunTransitionError
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType, encode_sse
from scriptnow.platform.source_distillation import (
    EvidenceInput,
    SourceDistillationError,
    SourceDistillationService,
)
from scriptnow.platform.source_distillation_runner import (
    AgentRuntimeDistillationAnalyzer,
    SourceDistillationRunner,
    source_distiller_skill_key,
)
from scriptnow.platform.source_text import extract_source_text
from scriptnow.platform.workspace import LocalWorkspaceService, StoredFile, WorkspaceViolation



async def _sync_project_plan_direction(
    session: AsyncSession,
    project_id: str,
    medium: ProjectMedium,
    direction: dict[str, str],
) -> None:
    table_name = "script_plans" if medium == ProjectMedium.SCRIPT else "novel_plans"
    exists = await session.execute(
        text(f"SELECT 1 FROM {table_name} WHERE project_id = :project_id"),
        {"project_id": project_id},
    )
    if exists.scalar_one_or_none() is None:
        return
    await session.execute(
        text(f"UPDATE {table_name} SET direction = :direction WHERE project_id = :project_id"),
        {
            "project_id": project_id,
            "direction": json.dumps(direction, ensure_ascii=False),
        },
    )


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    medium: ProjectMedium
    source_mode: ProjectSource = ProjectSource.ORIGINAL
    workflow_kind: ProjectWorkflow | None = None
    direction: dict[str, str] = Field(default_factory=dict)


class DeleteProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_name: str = Field(min_length=1, max_length=200)


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)


class UpdateDirectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: dict[str, str]


class InspirationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    medium: ProjectMedium
    seed: str = Field(min_length=2, max_length=1000)
    language: str = Field(default="zh-CN", min_length=2, max_length=20)
    genres: list[str] = Field(default_factory=list, max_length=12)


class InspirationResponse(BaseModel):
    title: str
    premise: str
    tone: str
    world_setting: str
    genre_suggestions: list[str]
    questions: list[str]
    model_key: str
    skill_keys: list[str]


class ProjectResponse(BaseModel):
    id: str
    name: str
    medium: str
    source_mode: str
    workflow_kind: str
    direction: dict[str, object]


class StartMockRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_key: str = "writer"
    idempotency_key: str = Field(min_length=1, max_length=120)
    max_tokens: int = Field(default=1000, ge=1, le=100_000)


class RunResponse(BaseModel):
    id: str
    status: str
    config_fingerprint: str
    billed_tokens: int


class FileResponse(BaseModel):
    id: str
    original_name: str
    media_type: str
    byte_size: int
    status: str


class RagHitResponse(BaseModel):
    chunk_id: str
    source_file_id: str
    source_name: str
    ordinal: int
    excerpt: str
    score: int


class StartDistillationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_file_ids: list[str] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=120)


class ExecuteDistillationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    max_tokens: int = Field(default=250_000, ge=1, le=2_000_000)
    external_processing_consent: bool = False
    consent_version: str = Field(default="source-processing-v1", max_length=80)


class DistillationEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_key: str = Field(min_length=1, max_length=160)
    source_file_id: str
    chunk_id: str
    source_unit: str = Field(min_length=1, max_length=240)
    ordinal: int = Field(ge=0)
    dimension: str
    claim: str = Field(min_length=1)
    confidence: int = Field(ge=0, le=100)
    inference: bool = False
    related_evidence_ids: list[str] = Field(default_factory=list)
    contradiction_group: str | None = Field(default=None, max_length=120)


class DistillationCheckpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    next_pass: str
    processed_chunk_ids: list[str] = Field(default_factory=list)
    coverage: dict[str, object] = Field(default_factory=dict)


class DistillationCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: dict[str, object]
    evidence_ids: list[str] = Field(min_length=1)
    conflicts: list[dict[str, object]] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    ready_with_gaps: bool = False


class DistillationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    feedback: str | None = Field(default=None, max_length=4000)


class AccountSummaryResponse(BaseModel):
    tenant_name: str
    tier_code: str
    tier_name: str
    monthly_price: float
    monthly_quota: int
    monthly_remaining: int
    monthly_used: int
    credits_available: int
    currency: str
    period_key: str


class CreatorModelResponse(BaseModel):
    id: str
    key: str
    display_name: str
    provider_name: str
    minimum_tier: str
    context_window: int
    available: bool
    reason: str | None = None


class AgentTeamMemberResponse(BaseModel):
    role_key: str
    system_name: str
    custom_name: str | None
    soul_base: str
    soul_override: str | None
    model_id: str
    default_model_id: str


class UpdateAgentTeamMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    custom_name: str | None = Field(default=None, max_length=80)
    soul_override: str | None = Field(default=None, max_length=2000)
    model_id: str | None = None


ProjectInitializer = Callable[[AsyncSession, ProjectModel], Awaitable[None]]


def create_core_router(
    database: Database,
    auth: AuthService,
    settings: Settings,
    project_initializer: ProjectInitializer | None = None,
) -> APIRouter:
    router = APIRouter(tags=["platform"])
    runs = RunCoordinator(database)
    events = PersistentRunEventLog(database)
    billing = BillingService(database, enforce_limits=settings.enforce_agent_budget)
    factory = AgentFactory(database)
    audit = AuditService(database)
    workspace = LocalWorkspaceService(
        database,
        Path(settings.workspace_root),
        max_file_bytes=settings.upload_max_file_bytes,
        max_project_bytes=settings.upload_max_project_bytes,
        max_project_files=settings.upload_max_project_files,
    )
    rag = RagService(database)
    distillations = SourceDistillationService(database)
    agent_runtime = AgentRuntime(database, settings)

    async def execute_distillation(
        *,
        tenant_id: str,
        project_id: str,
        distillation_id: str,
        run_id: str,
        reservation_id: str,
    ) -> None:
        try:
            await runs.transition(tenant_id=tenant_id, run_id=run_id, target=RunStatus.RUNNING)
            await events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="source-distillation.started",
                type=RunEventType.SYSTEM,
                payload={
                    "title": "正在多轮分析来源作品",
                    "distillation_id": distillation_id,
                },
                correlation_id=project_id,
            )

            async def record_usage(
                pass_key: str, call_index: int, result: AgentRuntimeResult
            ) -> None:
                await billing.record_model_call(
                    reservation_id=reservation_id,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    framework_event_id=f"source-distillation:{pass_key}:{call_index}",
                    trace_id=run_id,
                    agent_role="reviewer",
                    model_key=result.model_key,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    input_price_per_million=result.input_price_per_million,
                    output_price_per_million=result.output_price_per_million,
                )

            async with database.session() as session:
                distillation_project = await session.get(ProjectModel, project_id)
            skill_key = source_distiller_skill_key(
                str(distillation_project.medium) if distillation_project else "novel"
            )
            runner = SourceDistillationRunner(
                database,
                AgentRuntimeDistillationAnalyzer(
                    agent_runtime,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    usage_sink=record_usage,
                    skill_key=skill_key,
                    selected_model_id=settings.distillation_extract_model_id,
                ),
                evidence_batch_size=settings.distillation_evidence_batch_size,
                extract_concurrency=settings.distillation_extract_concurrency,
            )
            result = await runner.run(tenant_id=tenant_id, distillation_id=distillation_id)
            await events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="source-distillation.candidate-ready",
                type=RunEventType.DECISION,
                payload={
                    "title": "来源画像候选已生成，等待你的确认",
                    "distillation_id": result.distillation_id,
                    "profile_id": result.profile_id,
                    "evidence_count": result.evidence_count,
                    "processed_chunks": result.processed_chunks,
                },
                correlation_id=project_id,
            )
            await runs.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.WAITING,
                waiting_reason="source_profile_decision",
            )
        except Exception as error:
            await events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="source-distillation.failed",
                type=RunEventType.TERMINAL,
                payload={
                    "title": "来源作品分析暂时中断，可从检查点重试",
                    "error": user_facing_exception_message(error),
                },
                correlation_id=project_id,
            )
            with suppress(RunTransitionError):
                await runs.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.FAILED,
                    error_code="source_distillation_failed",
                )
        finally:
            with suppress(BillingError):
                await billing.finalize(reservation_id)

    async def action_context(access_token: str | None, csrf_token: str | None):
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        if csrf_token is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            return await auth.authorize_action(access_token, csrf_token)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    async def read_context(access_token: str | None):
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            return await auth.validate_access(access_token)
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    @router.get("/creative-options/{medium}")
    async def get_creative_options(
        medium: ProjectMedium,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        await read_context(access_token)
        if str(medium) not in {"novel", "script"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported medium")
        return {
            "medium": str(medium),
            "genres": creative_genre_options(factory.skill_catalog, medium=str(medium)),
            "catalog_fingerprint": factory.skill_catalog.fingerprint(
                domain=str(medium), role_key="director"
            ),
        }

    @router.post("/creative-inspiration", response_model=InspirationResponse)
    async def create_inspiration(
        body: InspirationRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> InspirationResponse:
        context = await action_context(access_token, csrf_token)
        if str(body.medium) not in {"novel", "script"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported medium")
        try:
            result = await agent_runtime.inspire(
                tenant_id=str(context.tenant_id),
                medium=str(body.medium),
                seed=body.seed.strip(),
                language=body.language,
                genres=tuple(body.genres),
            )
            raw = result.text.strip()
            if raw.startswith("```"):
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("response is not an object")
            resolved = await factory.preview_for_tenant(
                tenant_id=str(context.tenant_id),
                role_key="director",
                medium=str(body.medium),
                direction={"language": body.language, "genres": body.genres},
                stage="ideation",
            )
            response = InspirationResponse(
                title=str(payload.get("title") or "").strip(),
                premise=str(payload.get("premise") or "").strip(),
                tone=str(payload.get("tone") or "").strip(),
                world_setting=str(payload.get("world_setting") or "").strip(),
                genre_suggestions=[
                    str(value).strip()
                    for value in payload.get("genre_suggestions", [])
                    if str(value).strip()
                ],
                questions=[
                    str(value).strip()
                    for value in payload.get("questions", [])[:3]
                    if str(value).strip()
                ],
                model_key=result.model_key,
                skill_keys=list(resolved.values.get("skill_keys") or []),
            )
            if not response.premise:
                raise ValueError("premise is empty")
        except (AgentRuntimeError, RuntimeConfigError, ValueError, json.JSONDecodeError) as error:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "这次没有生成完整的创作方向。你的想法仍在，可以重新生成。",
            ) from error
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="creative.inspiration",
            resource_type="creative_preview",
            resource_id=result.config_fingerprint,
            outcome="succeeded",
            correlation_id=result.config_fingerprint,
        )
        return response

    @router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
    async def create_project(
        body: CreateProjectRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> ProjectResponse:
        context = await action_context(access_token, csrf_token)
        direction = body.direction or {}
        workflow_kind = body.workflow_kind or (
            ProjectWorkflow.ADAPTATION
            if body.source_mode == ProjectSource.ADAPTATION
            else ProjectWorkflow.ORIGINAL
        )
        if (
            workflow_kind == ProjectWorkflow.CROSS_CULTURAL_RECREATION
            and body.medium != ProjectMedium.NOVEL
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "故事归化当前仅支持小说作品",
            )
        for key in ("volume_one", "volume_two", "chapter_target_words", "target_length"):
            if key in direction and not isinstance(direction[key], str):
                direction[key] = str(direction[key])
        async with database.session() as session:
            project = ProjectModel(
                tenant_id=str(context.tenant_id),
                name=body.name.strip(),
                medium=body.medium,
                source_mode=body.source_mode,
                workflow_kind=workflow_kind,
                direction=direction,
            )
            session.add(project)
            await session.flush()
            if project_initializer is not None:
                await project_initializer(session, project)
            response = ProjectResponse(
                id=project.id,
                name=project.name,
                medium=str(project.medium),
                source_mode=str(project.source_mode),
                workflow_kind=str(project.workflow_kind),
                direction=dict(project.direction),
            )
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="project.create",
            resource_type="project",
            resource_id=response.id,
            outcome="succeeded",
            correlation_id=response.id,
        )
        return response

    @router.get("/projects", response_model=list[ProjectResponse])
    async def list_projects(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[ProjectResponse]:
        context = await read_context(access_token)
        async with database.session() as session:
            projects = (
                await session.scalars(
                    select(ProjectModel)
                    .where(
                        ProjectModel.tenant_id == str(context.tenant_id),
                        ProjectModel.deleted_at.is_(None),
                    )
                    .order_by(ProjectModel.created_at)
                )
            ).all()
            return [
                ProjectResponse(
                    id=item.id,
                    name=item.name,
                    medium=str(item.medium),
                    source_mode=str(item.source_mode),
                    workflow_kind=str(item.workflow_kind),
                    direction=dict(item.direction),
                )
                for item in projects
            ]

    @router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_project(
        project_id: str,
        body: DeleteProjectRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            project = await _tenant_project(session, tenant_id, project_id)
            if body.confirmation_name != project.name:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "输入的项目名称不一致，未执行删除",
                )
            active_run = (
                await session.scalars(
                    select(ProjectRunModel.id).where(
                        ProjectRunModel.project_id == project_id,
                        ProjectRunModel.status.in_(
                            (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING)
                        ),
                    )
                )
            ).first()
            if active_run is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "项目仍有 Agent 任务在运行，请先取消或等待任务结束",
                )
            project.deleted_at = datetime.now(UTC)
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="project.delete",
            resource_type="project",
            resource_id=project_id,
            outcome="succeeded",
            correlation_id=project_id,
            details={"mode": "recoverable"},
        )

    @router.patch("/projects/{project_id}", response_model=ProjectResponse)
    async def update_project(
        project_id: str,
        body: UpdateProjectRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> ProjectResponse:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)

        async with database.session() as session:
            project = await _tenant_project(session, tenant_id, project_id)
            if body.name is not None:
                project.name = body.name
            await audit.record(
                tenant_id=tenant_id,
                actor_id=str(context.user_id),
                action="project.update",
                resource_type="project",
                resource_id=project_id,
                outcome="succeeded",
                correlation_id=project_id,
            )
        return ProjectResponse(
            id=project_id,
            name=project.name,
            medium=str(project.medium),
            source_mode=str(project.source_mode),
            workflow_kind=str(project.workflow_kind),
            direction=project.direction,
        )

    @router.patch("/projects/{project_id}/direction", response_model=ProjectResponse)
    async def update_project_direction(
        project_id: str,
        body: UpdateDirectionRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> ProjectResponse:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            project = await _tenant_project(session, tenant_id, project_id)
            merged = dict(project.direction)
            merged.update(body.direction)
            project.direction = merged
            await _sync_project_plan_direction(session, project_id, project.medium, merged)
            await audit.record(
                tenant_id=tenant_id,
                actor_id=str(context.user_id),
                action="project.direction.update",
                resource_type="project",
                resource_id=project_id,
                outcome="succeeded",
                correlation_id=project_id,
            )
        return ProjectResponse(
            id=project_id,
            name=project.name,
            medium=str(project.medium),
            source_mode=str(project.source_mode),
            workflow_kind=str(project.workflow_kind),
            direction=merged,
        )

    @router.get("/account/summary", response_model=AccountSummaryResponse)
    async def account_summary(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> AccountSummaryResponse:
        context = await read_context(access_token)
        async with database.session() as session:
            tenant = await session.get(TenantModel, str(context.tenant_id))
            if tenant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
            tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
            ).one_or_none()
            account = (
                await session.scalars(
                    select(TokenAccountModel).where(
                        TokenAccountModel.tenant_id == tenant.id,
                        TokenAccountModel.tier == tenant.tier,
                    )
                )
            ).one_or_none()
            if tier is None or account is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "account configuration incomplete")
            monthly_remaining = max(0, account.monthly_available)
            return AccountSummaryResponse(
                tenant_name=tenant.name,
                tier_code=tier.code,
                tier_name=tier.name,
                monthly_price=float(tier.monthly_price),
                monthly_quota=tier.monthly_token_quota,
                monthly_remaining=monthly_remaining,
                monthly_used=max(0, tier.monthly_token_quota - monthly_remaining),
                credits_available=account.credits_available,
                currency=account.currency,
                period_key=account.period_key,
            )

    @router.get("/projects/{project_id}/models", response_model=list[CreatorModelResponse])
    async def creator_models(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[CreatorModelResponse]:
        context = await read_context(access_token)
        async with database.session() as session:
            tenant = await session.get(TenantModel, str(context.tenant_id))
            if tenant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
            await _tenant_project(session, tenant.id, project_id)
            current_tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
            ).one_or_none()
            if current_tier is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "tenant tier is not configured")
            tiers = {item.id: item for item in (await session.scalars(select(TierModel))).all()}
            providers = {
                item.id: item for item in (await session.scalars(select(ProviderModel))).all()
            }
            models = (
                await session.scalars(
                    select(LanguageModelModel).order_by(LanguageModelModel.created_at)
                )
            ).all()
            response: list[CreatorModelResponse] = []
            for model in models:
                provider = providers.get(model.provider_id)
                minimum = tiers.get(model.min_tier_id)
                if provider is None or minimum is None:
                    continue
                reason = None
                if not model.enabled:
                    reason = "disabled"
                elif provider.status != ProviderStatus.CONNECTED:
                    reason = "provider_unavailable"
                elif current_tier.rank < minimum.rank:
                    reason = "upgrade_required"
                response.append(
                    CreatorModelResponse(
                        id=model.id,
                        key=model.key,
                        display_name=model.display_name,
                        provider_name=provider.name,
                        minimum_tier=minimum.code,
                        context_window=model.context_window,
                        available=reason is None,
                        reason=reason,
                    )
                )
            return response

    @router.get("/projects/{project_id}/agent-team", response_model=list[AgentTeamMemberResponse])
    async def agent_team(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[AgentTeamMemberResponse]:
        context = await read_context(access_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            await _tenant_project(session, tenant_id, project_id)
            templates = (
                await session.scalars(
                    select(AgentTemplateVersionModel)
                    .where(AgentTemplateVersionModel.published.is_(True))
                    .order_by(
                        AgentTemplateVersionModel.role_key,
                        AgentTemplateVersionModel.version.desc(),
                    )
                )
            ).all()
            latest = {}
            for template in templates:
                latest.setdefault(template.role_key, template)
            configs = {
                item.role_key: item
                for item in (
                    await session.scalars(
                        select(TenantAgentConfigModel).where(
                            TenantAgentConfigModel.tenant_id == tenant_id,
                            TenantAgentConfigModel.project_id == project_id,
                        )
                    )
                ).all()
            }
            names = {
                "director": "策划 Director",
                "architect": "结构 Architect",
                "writer": "写作 Writer",
                "reviewer": "审读 Reviewer",
            }
            return [
                AgentTeamMemberResponse(
                    role_key=role_key,
                    system_name=names.get(role_key, role_key),
                    custom_name=configs.get(role_key).custom_name if role_key in configs else None,
                    soul_base=template.soul,
                    soul_override=configs.get(role_key).soul_override
                    if role_key in configs
                    else None,
                    model_id=(configs[role_key].model_id or template.default_model_id)
                    if role_key in configs
                    else template.default_model_id,
                    default_model_id=template.default_model_id,
                )
                for role_key, template in latest.items()
            ]

    @router.put(
        "/projects/{project_id}/agent-team/{role_key}",
        response_model=AgentTeamMemberResponse,
    )
    async def update_agent_team_member(
        project_id: str,
        role_key: str,
        body: UpdateAgentTeamMemberRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AgentTeamMemberResponse:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            await _tenant_project(session, tenant_id, project_id)
            template = (
                await session.scalars(
                    select(AgentTemplateVersionModel)
                    .where(
                        AgentTemplateVersionModel.role_key == role_key,
                        AgentTemplateVersionModel.published.is_(True),
                    )
                    .order_by(AgentTemplateVersionModel.version.desc())
                )
            ).first()
            if template is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "agent role not found")
            model_id = body.model_id or template.default_model_id
            await _available_model(session, tenant_id, model_id)
            config = (
                await session.scalars(
                    select(TenantAgentConfigModel).where(
                        TenantAgentConfigModel.tenant_id == tenant_id,
                        TenantAgentConfigModel.project_id == project_id,
                        TenantAgentConfigModel.role_key == role_key,
                    )
                )
            ).one_or_none()
            if config is None:
                config = TenantAgentConfigModel(
                    tenant_id=tenant_id, project_id=project_id, role_key=role_key
                )
                session.add(config)
            config.custom_name = body.custom_name.strip() if body.custom_name else None
            config.soul_override = body.soul_override.strip() if body.soul_override else None
            config.model_id = model_id
            await session.flush()
            response = AgentTeamMemberResponse(
                role_key=role_key,
                system_name={
                    "director": "策划 Director",
                    "architect": "结构 Architect",
                    "writer": "写作 Writer",
                    "reviewer": "审读 Reviewer",
                }.get(role_key, role_key),
                custom_name=config.custom_name,
                soul_base=template.soul,
                soul_override=config.soul_override,
                model_id=model_id,
                default_model_id=template.default_model_id,
            )
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="agent_team.update",
            resource_type="tenant_agent_config",
            resource_id=f"{project_id}:{role_key}",
            outcome="succeeded",
            correlation_id=project_id,
            details={"model_id": model_id},
        )
        return response

    @router.delete(
        "/projects/{project_id}/agent-team/{role_key}", status_code=status.HTTP_204_NO_CONTENT
    )
    async def reset_agent_team_member(
        project_id: str,
        role_key: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            await _tenant_project(session, tenant_id, project_id)
            config = (
                await session.scalars(
                    select(TenantAgentConfigModel).where(
                        TenantAgentConfigModel.tenant_id == tenant_id,
                        TenantAgentConfigModel.project_id == project_id,
                        TenantAgentConfigModel.role_key == role_key,
                    )
                )
            ).one_or_none()
            if config is not None:
                await session.delete(config)
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="agent_team.reset",
            resource_type="tenant_agent_config",
            resource_id=f"{project_id}:{role_key}",
            outcome="succeeded",
            correlation_id=project_id,
        )

    @router.post(
        "/projects/{project_id}/files",
        response_model=FileResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_file(
        project_id: str,
        file: Annotated[UploadFile, File()],
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> FileResponse:
        context = await action_context(access_token, csrf_token)
        content = await file.read(settings.upload_max_file_bytes + 1)
        try:
            stored = await workspace.upload(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                actor_id=str(context.user_id),
                filename=file.filename or "upload",
                content=content,
                correlation_id=project_id,
            )
        except WorkspaceViolation as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        if stored.status == "ready":
            try:
                parsed_text = extract_source_text(content, stored.media_type)
            except Exception as error:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "source file could not be parsed",
                ) from error
            if parsed_text:
                await rag.index_text(
                    tenant_id=str(context.tenant_id),
                    project_id=project_id,
                    source_file_id=stored.id,
                    parsed_text=parsed_text,
                )
        return _file_response(stored)

    @router.get("/projects/{project_id}/files", response_model=list[FileResponse])
    async def list_files(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[FileResponse]:
        context = await read_context(access_token)
        try:
            stored = await workspace.list_files(
                tenant_id=str(context.tenant_id), project_id=project_id
            )
        except WorkspaceViolation as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found") from error
        return [_file_response(item) for item in stored]

    @router.delete("/projects/{project_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_file(
        project_id: str,
        file_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        context = await action_context(access_token, csrf_token)
        try:
            await workspace.delete_file(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                file_id=file_id,
                actor_id=str(context.user_id),
                correlation_id=project_id,
            )
        except WorkspaceViolation as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found") from error

    @router.get("/projects/{project_id}/rag/search", response_model=list[RagHitResponse])
    async def search_sources(
        project_id: str,
        q: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[RagHitResponse]:
        context = await read_context(access_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            project = await _tenant_project(session, tenant_id, project_id)
            if project.source_mode != ProjectSource.ADAPTATION:
                raise HTTPException(status.HTTP_409_CONFLICT, "source search requires adaptation")
            files = {
                item.id: item.original_name
                for item in (
                    await session.scalars(
                        select(WorkspaceFileModel).where(
                            WorkspaceFileModel.tenant_id == tenant_id,
                            WorkspaceFileModel.project_id == project_id,
                        )
                    )
                ).all()
            }
        hits = (
            await rag.search(tenant_id=tenant_id, project_id=project_id, query=q)
            if q.strip()
            else await rag.browse(tenant_id=tenant_id, project_id=project_id)
        )
        if not hits:
            for file_id in files:
                try:
                    path = await workspace.resolve_ready_file(
                        tenant_id=tenant_id, project_id=project_id, file_id=file_id
                    )
                    async with database.session() as session:
                        model = await session.get(WorkspaceFileModel, file_id)
                    if model is None:
                        continue
                    parsed_text = extract_source_text(path.read_bytes(), model.media_type)
                    if parsed_text:
                        await rag.index_text(
                            tenant_id=tenant_id,
                            project_id=project_id,
                            source_file_id=file_id,
                            parsed_text=parsed_text,
                        )
                except (OSError, WorkspaceViolation, ValueError):
                    continue
            hits = (
                await rag.search(tenant_id=tenant_id, project_id=project_id, query=q)
                if q.strip()
                else await rag.browse(tenant_id=tenant_id, project_id=project_id)
            )
        return [
            RagHitResponse(
                chunk_id=hit.chunk_id,
                source_file_id=hit.source_file_id,
                source_name=files.get(hit.source_file_id, "来源文件"),
                ordinal=hit.ordinal,
                excerpt=hit.content[:500],
                score=hit.score,
            )
            for hit in hits
        ]

    @router.post("/projects/{project_id}/source-distillations")
    async def start_source_distillation(
        project_id: str,
        body: StartDistillationRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        try:
            run = await distillations.start(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                source_file_ids=body.source_file_ids,
                idempotency_key=body.idempotency_key,
            )
        except SourceDistillationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "id": run.id,
            "status": run.status,
            "pass_key": run.pass_key,
            "checkpoint": run.checkpoint,
            "coverage": run.coverage,
        }

    @router.post("/projects/{project_id}/source-distillations/{distillation_id}/execute")
    async def execute_source_distillation(
        project_id: str,
        distillation_id: str,
        body: ExecuteDistillationRequest,
        background_tasks: BackgroundTasks,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)
        if not body.external_processing_consent or body.consent_version != "source-processing-v1":
            raise HTTPException(
                status.HTTP_428_PRECONDITION_REQUIRED,
                (
                    "请先确认：来源手稿将分批发送至当前配置的第三方模型 Provider，"
                    "仅用于本项目的证据提取、跨章分析与候选创作画像生成。"
                ),
            )
        async with database.session() as session:
            project = await _tenant_project(session, tenant_id, project_id)
            scoped_run = await session.get(SourceDistillationModel, distillation_id)
            if (
                scoped_run is None
                or scoped_run.tenant_id != tenant_id
                or scoped_run.project_id != project_id
            ):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "distillation not found")
        skill_key = source_distiller_skill_key(str(project.medium))
        try:
            project_run = await runs.enqueue(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=body.idempotency_key,
            )
        except RunTransitionError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        try:
            runtime_snapshot = await factory.snapshot_for_run(
                tenant_id=tenant_id,
                run_id=project_run.id,
                role_key="reviewer",
                stage_override="source-analysis",
                explicit_skill_keys=(skill_key,),
            )
        except RuntimeConfigError as error:
            with suppress(RunTransitionError):
                await runs.transition(
                    tenant_id=tenant_id,
                    run_id=project_run.id,
                    target=RunStatus.CANCELLED,
                )
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        try:
            reservation = await billing.reserve(
                tenant_id=tenant_id,
                run_id=project_run.id,
                idempotency_key=f"source-distillation:{body.idempotency_key}",
                tier=(await _tenant(database, tenant_id)).tier,
                max_tokens=body.max_tokens,
                ttl_minutes=120,
            )
        except PaymentRequired as error:
            with suppress(RunTransitionError):
                await runs.transition(
                    tenant_id=tenant_id,
                    run_id=project_run.id,
                    target=RunStatus.CANCELLED,
                )
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(error)) from error
        except BillingError as error:
            with suppress(RunTransitionError):
                await runs.transition(
                    tenant_id=tenant_id,
                    run_id=project_run.id,
                    target=RunStatus.CANCELLED,
                )
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        await audit.record(
            tenant_id=tenant_id,
            actor_id=str(context.user_id),
            action="source_distillation.external_processing_authorized",
            resource_type="source_distillation",
            resource_id=distillation_id,
            outcome="succeeded",
            correlation_id=project_run.id,
            details={
                "consent_version": body.consent_version,
                "provider_key": runtime_snapshot.values.get("provider_key"),
                "model_key": runtime_snapshot.values.get("model_key"),
                "source_file_ids": scoped_run.source_file_ids,
            },
        )
        if project_run.status == RunStatus.QUEUED:
            background_tasks.add_task(
                execute_distillation,
                tenant_id=tenant_id,
                project_id=project_id,
                distillation_id=distillation_id,
                run_id=project_run.id,
                reservation_id=reservation.id,
            )
        return {
            "distillation_id": distillation_id,
            "run_id": project_run.id,
            "status": project_run.status,
        }

    @router.get("/projects/{project_id}/source-distillations/{distillation_id}/execution-preflight")
    async def source_distillation_execution_preflight(
        project_id: str,
        distillation_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        context = await read_context(access_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            await _tenant_project(session, tenant_id, project_id)
            run = await session.get(SourceDistillationModel, distillation_id)
            if run is None or run.tenant_id != tenant_id or run.project_id != project_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "distillation not found")
            files = list(
                (
                    await session.scalars(
                        select(WorkspaceFileModel).where(
                            WorkspaceFileModel.id.in_(run.source_file_ids)
                        )
                    )
                ).all()
            )
        runtime_status = await agent_runtime.status(tenant_id=tenant_id, project_id=project_id)
        reviewer = dict(dict(runtime_status.get("roles") or {}).get("reviewer") or {})
        return {
            "distillation_id": run.id,
            "external_processing": True,
            "consent_version": "source-processing-v1",
            "purpose": ["证据提取", "跨章分析", "冲突与缺口检查", "候选创作画像"],
            "provider_key": reviewer.get("provider_key"),
            "model_key": reviewer.get("model_key"),
            "runtime_connected": reviewer.get("connected", False),
            "sources": [
                {"id": item.id, "name": item.original_name, "byte_size": item.byte_size}
                for item in files
            ],
            "processed_chunks": len(dict(run.checkpoint).get("processed_chunk_ids") or []),
            "total_chunks": dict(run.coverage).get("total_chunks", 0),
        }

    @router.get("/projects/{project_id}/source-distillations/latest")
    async def get_latest_source_distillation(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object] | None:
        context = await read_context(access_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            await _tenant_project(session, tenant_id, project_id)
            run = (
                await session.scalars(
                    select(SourceDistillationModel)
                    .where(
                        SourceDistillationModel.tenant_id == tenant_id,
                        SourceDistillationModel.project_id == project_id,
                    )
                    .order_by(SourceDistillationModel.created_at.desc())
                )
            ).first()
        if run is None:
            return None
        return {
            "id": run.id,
            "status": run.status,
            "pass_key": run.pass_key,
            "checkpoint": run.checkpoint,
            "coverage": run.coverage,
        }

    @router.get("/projects/{project_id}/source-distillations/{distillation_id}")
    async def get_source_distillation(
        project_id: str,
        distillation_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        context = await read_context(access_token)
        tenant_id = str(context.tenant_id)
        async with database.session() as session:
            await _tenant_project(session, tenant_id, project_id)
            run = await session.get(SourceDistillationModel, distillation_id)
            if run is None or run.tenant_id != tenant_id or run.project_id != project_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "distillation not found")
            profile = (
                await session.scalars(
                    select(SourceProfileModel)
                    .where(SourceProfileModel.distillation_id == run.id)
                    .order_by(SourceProfileModel.version.desc())
                )
            ).first()
            evidence = (
                list(
                    (
                        await session.scalars(
                            select(SourceEvidenceModel)
                            .where(SourceEvidenceModel.distillation_id == run.id)
                            .order_by(SourceEvidenceModel.created_at)
                        )
                    ).all()
                )
                if profile
                else []
            )
            return {
                "id": run.id,
                "status": run.status,
                "pass_key": run.pass_key,
                "checkpoint": run.checkpoint,
                "coverage": run.coverage,
                "candidate": (
                    {
                        "id": profile.id,
                        "version": profile.version,
                        "decision": profile.decision,
                        "profile": profile.profile,
                        "conflicts": profile.conflicts,
                        "exclusions": profile.exclusions,
                        "evidence": [
                            {
                                "id": item.id,
                                "source_file_id": item.source_file_id,
                                "chunk_id": item.chunk_id,
                                "source_unit": item.source_unit,
                                "dimension": item.dimension,
                                "claim": item.claim,
                                "confidence": item.confidence,
                                "inference": item.inference,
                            }
                            for item in evidence
                            if item.id in profile.evidence_ids
                        ],
                    }
                    if profile
                    else None
                ),
            }

    @router.post("/projects/{project_id}/source-distillations/{distillation_id}/evidence")
    async def add_distillation_evidence(
        project_id: str,
        distillation_id: str,
        body: DistillationEvidenceRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        async with database.session() as session:
            await _tenant_project(session, str(context.tenant_id), project_id)
            scoped_run = await session.get(SourceDistillationModel, distillation_id)
            if scoped_run is None or scoped_run.project_id != project_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "distillation not found")
        try:
            evidence = await distillations.record_evidence(
                tenant_id=str(context.tenant_id),
                distillation_id=distillation_id,
                item=EvidenceInput(**body.model_dump()),
            )
        except SourceDistillationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {"id": evidence.id, "evidence_key": evidence.evidence_key}

    @router.post("/projects/{project_id}/source-distillations/{distillation_id}/checkpoint")
    async def checkpoint_source_distillation(
        project_id: str,
        distillation_id: str,
        body: DistillationCheckpointRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        async with database.session() as session:
            await _tenant_project(session, str(context.tenant_id), project_id)
            scoped_run = await session.get(SourceDistillationModel, distillation_id)
            if scoped_run is None or scoped_run.project_id != project_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "distillation not found")
        try:
            run = await distillations.checkpoint(
                tenant_id=str(context.tenant_id),
                distillation_id=distillation_id,
                next_pass=body.next_pass,
                processed_chunk_ids=body.processed_chunk_ids,
                coverage=body.coverage,
            )
        except SourceDistillationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "id": run.id,
            "status": run.status,
            "pass_key": run.pass_key,
            "checkpoint": run.checkpoint,
            "coverage": run.coverage,
        }

    @router.post("/projects/{project_id}/source-distillations/{distillation_id}/candidate")
    async def create_distillation_candidate(
        project_id: str,
        distillation_id: str,
        body: DistillationCandidateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        async with database.session() as session:
            await _tenant_project(session, str(context.tenant_id), project_id)
            scoped_run = await session.get(SourceDistillationModel, distillation_id)
            if scoped_run is None or scoped_run.project_id != project_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "distillation not found")
        try:
            candidate = await distillations.create_candidate(
                tenant_id=str(context.tenant_id),
                distillation_id=distillation_id,
                **body.model_dump(),
            )
        except SourceDistillationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "id": candidate.id,
            "version": candidate.version,
            "decision": candidate.decision,
            "profile": candidate.profile,
        }

    @router.post("/projects/{project_id}/source-profiles/{profile_id}/decision")
    async def decide_source_profile(
        project_id: str,
        profile_id: str,
        body: DistillationDecisionRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        try:
            profile = await distillations.decide(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                profile_id=profile_id,
                approve=body.approve,
                feedback=body.feedback,
            )
        except SourceDistillationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        await audit.record(
            tenant_id=str(context.tenant_id),
            actor_id=str(context.user_id),
            action="source_profile.approve" if body.approve else "source_profile.reject",
            resource_type="source_profile",
            resource_id=profile.id,
            outcome="succeeded",
            correlation_id=project_id,
            details={"version": profile.version},
        )
        return {
            "id": profile.id,
            "version": profile.version,
            "decision": profile.decision,
            "profile": profile.profile,
        }

    @router.get("/projects/{project_id}/source-profiles/approved")
    async def get_approved_source_profile(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object] | None:
        context = await read_context(access_token)
        profile = await distillations.approved_profile(
            tenant_id=str(context.tenant_id), project_id=project_id
        )
        if profile is None:
            return None
        return {
            "id": profile.id,
            "version": profile.version,
            "profile": profile.profile,
            "evidence_ids": profile.evidence_ids,
            "conflicts": profile.conflicts,
            "exclusions": profile.exclusions,
        }

    @router.post("/projects/{project_id}/runs/mock", response_model=RunResponse)
    async def start_mock_run(
        project_id: str,
        body: StartMockRunRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> RunResponse:
        context = await action_context(access_token, csrf_token)
        tenant_id = str(context.tenant_id)
        try:
            run = await runs.enqueue(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=body.idempotency_key,
            )
            if run.status != RunStatus.QUEUED:
                async with database.session() as session:
                    existing = await session.get(ProjectRunModel, run.id)
                    assert existing is not None
                snapshot = await factory.snapshot_for_run(
                    tenant_id=tenant_id, run_id=run.id, role_key=body.role_key
                )
                return RunResponse(
                    id=run.id,
                    status=run.status,
                    config_fingerprint=snapshot.fingerprint,
                    billed_tokens=20,
                )
            snapshot = await factory.snapshot_for_run(
                tenant_id=tenant_id, run_id=run.id, role_key=body.role_key
            )
            reservation = await billing.reserve(
                tenant_id=tenant_id,
                run_id=run.id,
                idempotency_key=f"run:{body.idempotency_key}",
                tier=(await _tenant(database, tenant_id)).tier,
                max_tokens=body.max_tokens,
            )
            await runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
            await events.append(
                tenant_id=tenant_id,
                run_id=run.id,
                event_key="mock:reply",
                type=RunEventType.AGENT,
                payload={"delta": "Mock runtime completed", "mock": True},
                correlation_id=run.id,
            )
            async with database.session() as session:
                model = await session.get(LanguageModelModel, str(snapshot.values["model_id"]))
                assert model is not None
            await billing.record_model_call(
                reservation_id=reservation.id,
                tenant_id=tenant_id,
                run_id=run.id,
                framework_event_id="mock:model-call",
                trace_id=run.id,
                agent_role=body.role_key,
                model_key=model.key,
                input_tokens=8,
                output_tokens=12,
                input_price_per_million=Decimal(str(model.input_price_per_million)),
                output_price_per_million=Decimal(str(model.output_price_per_million)),
            )
            finalized = await billing.finalize(reservation.id)
            completed = await runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            await events.append(
                tenant_id=tenant_id,
                run_id=run.id,
                event_key="mock:terminal",
                type=RunEventType.TERMINAL,
                payload={"status": "succeeded"},
                correlation_id=run.id,
            )
            await audit.record(
                tenant_id=tenant_id,
                actor_id=str(context.user_id),
                action="run.mock.complete",
                resource_type="project_run",
                resource_id=run.id,
                outcome="succeeded",
                correlation_id=run.id,
                details={"billed_tokens": finalized.actual_tokens or 0},
            )
            return RunResponse(
                id=run.id,
                status=completed.status,
                config_fingerprint=snapshot.fingerprint,
                billed_tokens=finalized.actual_tokens or 0,
            )
        except PaymentRequired as error:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(error)) from error
        except (BillingError, RunTransitionError, RuntimeConfigError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/runs/{run_id}")
    async def get_run_status(
        run_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        context = await read_context(access_token)
        async with database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != str(context.tenant_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
            return {
                "id": run.id,
                "project_id": run.project_id,
                "status": run.status,
                "waiting_reason": run.waiting_reason,
                "error_code": run.error_code,
                "state_version": run.state_version,
            }

    @router.get("/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        context = await read_context(access_token)
        try:
            pending = await events.after(
                tenant_id=str(context.tenant_id), run_id=run_id, cursor=last_event_id
            )
        except ValueError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run events not found") from error
        return StreamingResponse(
            (encode_sse(event) for event in pending), media_type="text/event-stream"
        )

    return router


async def _tenant(database: Database, tenant_id: str) -> TenantModel:
    async with database.session() as session:
        tenant = await session.get(TenantModel, tenant_id)
        if tenant is None:
            raise RunTransitionError("tenant does not exist")
        return tenant


async def _tenant_project(session: AsyncSession, tenant_id: str, project_id: str) -> ProjectModel:
    project = await session.get(ProjectModel, project_id)
    if project is None or project.tenant_id != tenant_id or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


async def _available_model(
    session: AsyncSession, tenant_id: str, model_id: str
) -> LanguageModelModel:
    tenant = await session.get(TenantModel, tenant_id)
    model = await session.get(LanguageModelModel, model_id)
    if tenant is None or model is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "model is unavailable")
    tier = (
        await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
    ).one_or_none()
    provider = await session.get(ProviderModel, model.provider_id)
    minimum = await session.get(TierModel, model.min_tier_id)
    if (
        tier is None
        or provider is None
        or minimum is None
        or not model.enabled
        or provider.status != ProviderStatus.CONNECTED
        or tier.rank < minimum.rank
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "model is unavailable")
    return model


def _file_response(stored: StoredFile) -> FileResponse:
    return FileResponse(
        id=stored.id,
        original_name=stored.original_name,
        media_type=stored.media_type,
        byte_size=stored.byte_size,
        status=stored.status,
    )
