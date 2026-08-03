from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from scriptnow.novel.review import create_novel_review_service, novel_scan_input
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.creative_delivery import CreativeDeliveryService
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectEventModel, ProjectModel, UserModel
from scriptnow.review.domain import FindingDomain, FindingDraft, FindingSeverity, FindingSource
from scriptnow.review.service import ReviewConflict, ReviewError
from scriptnow.script.review import create_script_review_service, script_ai_review_scene


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)


class HumanFindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_id: str
    base_revision_id: str
    element_id: str
    original_excerpt: str = Field(min_length=2)
    domain: FindingDomain
    severity: FindingSeverity
    anchor_type: str
    anchor_id: str
    diagnosis: str = Field(min_length=2)
    suggestion: str = Field(min_length=2)
    suggested_patch: dict[str, object]
    idempotency_key: str = Field(min_length=1, max_length=120)


def create_review_router(database: Database, auth: AuthService, settings) -> APIRouter:
    router = APIRouter(tags=["review"])
    deliveries = CreativeDeliveryService(database)

    async def context(access: str | None, csrf: str | None = None, *, write=False):
        if access is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        if write and csrf is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            return await (
                auth.authorize_action(access, csrf) if write else auth.validate_access(access)
            )
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    async def project_service(tenant_id: str, project_id: str):
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
        return (
            (project, create_script_review_service(database))
            if project.medium == "script"
            else (project, create_novel_review_service(database))
        )

    @router.post("/projects/{project_id}/units/{unit_id}/review/scan")
    async def scan(
        project_id: str,
        unit_id: str,
        body: ScanRequest,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        project, service = await project_service(str(actor.tenant_id), project_id)
        try:
            if project.medium == "script":
                from scriptnow.platform.agent_runtime import AgentRuntime
                from scriptnow.platform.billing import BillingService
                from scriptnow.platform.models import RunStatus, TenantModel
                from scriptnow.platform.run_coordinator import RunCoordinator
                tenant_id = str(actor.tenant_id)
                async with database.session() as session:
                    review_tenant = await session.get(TenantModel, tenant_id)
                    tier = review_tenant.tier if review_tenant is not None else "plus"
                runtime = AgentRuntime(database, settings)
                runs = RunCoordinator(database)
                billing = BillingService(
                    database, enforce_limits=settings.enforce_agent_budget
                )
                run = await runs.enqueue(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    idempotency_key=f"manual-quality-review:{unit_id}:{body.idempotency_key}",
                )
                await runs.transition(
                    tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING
                )
                reservation = await billing.reserve(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    idempotency_key=f"manual-quality-review:{unit_id}:{body.idempotency_key}",
                    tier=tier,
                    max_tokens=settings.script_agent_reserved_tokens,
                )
                result = await script_ai_review_scene(
                    database,
                    runtime,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    scene_id=unit_id,
                    run_id=run.id,
                )
                await billing.record_model_call(
                    reservation_id=reservation.id,
                    tenant_id=tenant_id,
                    run_id=run.id,
                    framework_event_id=f"manual-quality-review:{unit_id}",
                    trace_id=run.id,
                    agent_role="reviewer",
                    model_key=result.model_key,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    input_price_per_million=result.input_price_per_million,
                    output_price_per_million=result.output_price_per_million,
                )
                await billing.finalize(reservation.id)
                await runs.transition(
                    tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
                )
                findings = await service.list(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    filters={"unit_id": unit_id},
                )
                return {
                    "count": len(findings),
                    "severity_counts": {
                        "blocker": sum(1 for f in findings if f.severity == "blocker"),
                        "major": sum(1 for f in findings if f.severity == "major"),
                        "minor": sum(1 for f in findings if f.severity == "minor"),
                    },
                }
            revision_id, draft = await novel_scan_input(database, project_id, unit_id)
            hallucinated = draft.model_copy(update={"anchor_id": "invalid:hallucinated"})
            item = await service.scan_with_retry(
                tenant_id=str(actor.tenant_id),
                project_id=project_id,
                unit_id=unit_id,
                base_revision_id=revision_id,
                drafts=(hallucinated, draft),
                author="Script Editor" if project.medium == "script" else "Novel Editor",
                idempotency_key=body.idempotency_key,
            )
            if project.medium == "script":
                await deliveries.record(
                    tenant_id=str(actor.tenant_id),
                    project_id=project_id,
                    domain="script",
                    stage="quality_review",
                    kind="script_quality_report",
                    idempotency_key=f"script-review:{body.idempotency_key}",
                    payload={
                        "unit_id": unit_id,
                        "revision_id": revision_id,
                        "finding_id": item.id,
                        "severity": str(item.severity),
                        "diagnosis": item.diagnosis,
                        "suggestion": item.suggestion,
                    },
                )
            return _finding(item)
        except (ReviewError, RuntimeError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/projects/{project_id}/findings")
    async def findings(
        project_id: str,
        domain: str | None = Query(None),
        severity: str | None = Query(None),
        source: str | None = Query(None),
        finding_status: str | None = Query(None, alias="status"),
        unit_id: str | None = Query(None),
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        actor = await context(access)
        _, service = await project_service(str(actor.tenant_id), project_id)
        items = await service.list(
            tenant_id=str(actor.tenant_id),
            project_id=project_id,
            filters={
                "domain": domain,
                "severity": severity,
                "source": source,
                "status": finding_status,
                "unit_id": unit_id,
            },
        )
        return [_finding(item) for item in items]

    @router.get("/projects/{project_id}/review/timeline")
    async def timeline(
        project_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        actor = await context(access)
        await project_service(str(actor.tenant_id), project_id)
        async with database.session() as session:
            events = list(
                await session.scalars(
                    select(ProjectEventModel)
                    .where(ProjectEventModel.project_id == project_id)
                    .order_by(ProjectEventModel.sequence.desc())
                )
            )
        return [
            {
                "id": item.id,
                "sequence": item.sequence,
                "payload": item.payload,
                "occurred_at": item.occurred_at,
            }
            for item in events
            if str(item.payload.get("action", "")).startswith("review_")
        ]

    @router.post("/projects/{project_id}/findings")
    async def human_finding(
        project_id: str,
        body: HumanFindingRequest,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        _, service = await project_service(str(actor.tenant_id), project_id)
        async with database.session() as session:
            user = await session.get(UserModel, str(actor.user_id))
        draft = FindingDraft(
            domain=body.domain,
            severity=body.severity,
            anchor_type=body.anchor_type,
            anchor_id=body.anchor_id,
            element_id=body.element_id,
            original_excerpt=body.original_excerpt,
            locator={"element_id": body.element_id},
            diagnosis=body.diagnosis,
            suggestion=body.suggestion,
            suggested_patch=body.suggested_patch,
            confidence="high",
        )
        try:
            item = await service.create(
                tenant_id=str(actor.tenant_id),
                project_id=project_id,
                unit_id=body.unit_id,
                base_revision_id=body.base_revision_id,
                draft=draft,
                source=FindingSource.HUMAN,
                author=user.email if user else "Owner",
                idempotency_key=body.idempotency_key,
            )
            return _finding(item)
        except ReviewError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/projects/{project_id}/findings/{finding_id}/accept")
    async def accept(
        project_id: str,
        finding_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        _, service = await project_service(str(actor.tenant_id), project_id)
        try:
            return _finding(
                await service.accept(
                    tenant_id=str(actor.tenant_id), project_id=project_id, finding_id=finding_id
                )
            )
        except (ReviewError, ReviewConflict) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/projects/{project_id}/findings/{finding_id}/dismiss")
    async def dismiss(
        project_id: str,
        finding_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        _, service = await project_service(str(actor.tenant_id), project_id)
        try:
            return _finding(
                await service.dismiss(
                    tenant_id=str(actor.tenant_id), project_id=project_id, finding_id=finding_id
                )
            )
        except (ReviewError, ReviewConflict) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/projects/{project_id}/findings/{finding_id}/rollback")
    async def rollback(
        project_id: str,
        finding_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        _, service = await project_service(str(actor.tenant_id), project_id)
        try:
            return _finding(
                await service.rollback(
                    tenant_id=str(actor.tenant_id), project_id=project_id, finding_id=finding_id
                )
            )
        except (ReviewError, ReviewConflict) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return router


def _finding(item) -> dict[str, object]:
    return {
        key: getattr(item, key)
        for key in (
            "id",
            "project_id",
            "unit_id",
            "base_revision_id",
            "element_id",
            "domain",
            "severity",
            "source",
            "author",
            "anchor_type",
            "anchor_id",
            "anchor_note",
            "original_excerpt",
            "locator",
            "diagnosis",
            "suggestion",
            "suggested_patch",
            "confidence",
            "status",
            "stale_reason",
            "superseded_by",
            "created_at",
            "decided_at",
        )
    }
