from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from scriptflow_v7.dock.service import DockError, DockService
from scriptflow_v7.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptflow_v7.platform.auth_api import ACCESS_COOKIE
from scriptflow_v7.platform.billing import BillingError, PaymentRequired
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.run_coordinator import RunTransitionError
from scriptflow_v7.platform.run_events import PersistentRunEventLog, encode_sse


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=10_000)
    idempotency_key: str = Field(min_length=1, max_length=120)
    quote: dict[str, object] | None = None
    focus: dict[str, str] | None = None
    requires_confirmation: bool = False


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    approved: bool
    idempotency_key: str = Field(min_length=1, max_length=120)


def create_dock_router(database: Database, auth: AuthService, settings: Settings) -> APIRouter:
    router = APIRouter(tags=["dock"])
    dock = DockService(database, settings)
    run_events = PersistentRunEventLog(database)

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

    @router.get("/projects/{project_id}/events")
    async def events(
        project_id: str,
        after_id: str | None = None,
        types: str = Query(""),
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        actor = await context(access)
        try:
            return await dock.project_events(
                tenant_id=str(actor.tenant_id),
                project_id=project_id,
                after_id=after_id,
                types={item for item in types.split(",") if item},
            )
        except DockError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/projects/{project_id}/agents/{role}/messages")
    async def message(
        project_id: str,
        role: str,
        body: MessageRequest,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        try:
            return await dock.send_message(
                tenant_id=str(actor.tenant_id),
                project_id=project_id,
                actor_id=str(actor.user_id),
                role=role,
                content=body.content,
                quote=body.quote,
                focus=body.focus,
                idempotency_key=body.idempotency_key,
                requires_confirmation=body.requires_confirmation,
            )
        except PaymentRequired as error:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(error)) from error
        except (DockError, BillingError, RunTransitionError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/projects/{project_id}/agents/{role}/stream")
    async def stream(
        project_id: str,
        role: str,
        run_id: str,
        after_id: str | None = None,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> StreamingResponse:
        del project_id, role
        actor = await context(access)
        try:
            pending = await run_events.after(
                tenant_id=str(actor.tenant_id), run_id=run_id, cursor=after_id
            )
        except ValueError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "stream not found") from error
        return StreamingResponse(
            (encode_sse(item) for item in pending), media_type="text/event-stream"
        )

    @router.post("/projects/{project_id}/agents/{role}/confirm")
    async def confirm(
        project_id: str,
        role: str,
        body: ConfirmRequest,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        try:
            return await dock.confirm(
                tenant_id=str(actor.tenant_id),
                project_id=project_id,
                run_id=body.run_id,
                approved=body.approved,
                idempotency_key=body.idempotency_key,
                role=role,
            )
        except (DockError, BillingError, RunTransitionError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/projects/{project_id}/runs/{run_id}/cancel")
    async def cancel(
        project_id: str,
        run_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        try:
            return await dock.cancel(
                tenant_id=str(actor.tenant_id), project_id=project_id, run_id=run_id
            )
        except (DockError, BillingError, RunTransitionError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/projects/{project_id}/runs")
    async def runs(
        project_id: str, access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None
    ) -> list[dict[str, object]]:
        actor = await context(access)
        return await dock.project_runs(tenant_id=str(actor.tenant_id), project_id=project_id)

    @router.get("/projects/{project_id}/agents/{role}/transparency")
    async def transparency(
        project_id: str,
        role: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        actor = await context(access)
        try:
            return await dock.transparency(
                tenant_id=str(actor.tenant_id), project_id=project_id, role=role
            )
        except DockError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.get("/projects/{project_id}/agents/runtime-status")
    async def runtime_status(
        project_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        actor = await context(access)
        try:
            return await dock.runtime_status(tenant_id=str(actor.tenant_id), project_id=project_id)
        except DockError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    return router
