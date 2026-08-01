from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from scriptnow.platform.agent_runtime import (
    AgentRuntimeError,
    AgentRuntimeIncompleteError,
    AgentRuntimeTimeoutError,
)
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.review.workbench_service import ReviewWorkbenchError, ReviewWorkbenchService


class StandaloneReviewMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=1, max_length=100)
    language: str = Field(default="zh-CN", min_length=2, max_length=20)
    review_focus: Literal[
        "overall",
        "structure",
        "character",
        "pacing",
        "market",
        "adaptation",
    ] = "overall"


def create_review_workbench_router(
    database: Database,
    auth: AuthService,
    settings: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/review-agent", tags=["review-agent"])
    service = ReviewWorkbenchService(database, settings)

    async def context(access: str | None, csrf: str | None = None, *, write: bool = False):
        if access is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            return await (
                auth.authorize_action(access, csrf)
                if write
                else auth.validate_access(access)
            )
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    @router.get("/capabilities")
    async def capabilities(
        review_domain: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        actor = await context(access)
        try:
            return await service.capabilities(
                tenant_id=str(actor.tenant_id),
                review_domain=review_domain,
            )
        except ReviewWorkbenchError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/cases")
    async def create_case(
        file: Annotated[UploadFile, File()],
        document_kind: Annotated[str, Form()],
        review_domain: Annotated[str, Form()],
        title: Annotated[str | None, Form()] = None,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        content = await file.read(settings.upload_max_file_bytes + 1)
        if len(content) > settings.upload_max_file_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "uploaded file is too large")
        try:
            return await service.create_case(
                tenant_id=str(actor.tenant_id),
                filename=file.filename or "untitled",
                media_type=file.content_type or "application/octet-stream",
                content=content,
                document_kind=document_kind,
                review_domain=review_domain,
                title=title,
            )
        except ReviewWorkbenchError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error

    @router.get("/cases")
    async def list_cases(
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        actor = await context(access)
        return await service.list_cases(tenant_id=str(actor.tenant_id))

    @router.get("/cases/{case_id}")
    async def get_case(
        case_id: str,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        actor = await context(access)
        try:
            return await service.get_case(tenant_id=str(actor.tenant_id), case_id=case_id)
        except ReviewWorkbenchError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/cases/{case_id}/messages")
    async def send_message(
        case_id: str,
        body: StandaloneReviewMessageRequest,
        access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        actor = await context(access, csrf, write=True)
        try:
            return await service.send_message(
                tenant_id=str(actor.tenant_id),
                case_id=case_id,
                content=body.content,
                idempotency_key=body.idempotency_key,
                language=body.language,
                review_focus=body.review_focus,
            )
        except AgentRuntimeIncompleteError as error:
            detail = (
                "评审 Agent 未能在本轮完成结论。你的评审要求已保留，请直接重试。"
                if body.language.startswith("zh")
                else "The review agent did not complete this turn. "
                "Your request was retained; please retry."
            )
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from error
        except AgentRuntimeTimeoutError as error:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(error)) from error
        except AgentRuntimeError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        except ReviewWorkbenchError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return router
