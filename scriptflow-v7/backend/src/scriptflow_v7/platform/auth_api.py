from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, field_validator

from scriptflow_v7.platform.auth import (
    AuthenticationFailed,
    AuthService,
    AuthTokens,
    CsrfFailed,
    LoginRateLimited,
    RefreshTokenReuseDetected,
)
from scriptflow_v7.platform.config import Settings

ACCESS_COOKIE = "sf_access"
REFRESH_COOKIE = "sf_refresh"
CSRF_COOKIE = "sf_csrf"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip()
        local, separator, domain = normalized.partition("@")
        if not separator or not local or not domain or len(normalized) > 320:
            raise ValueError("invalid email address")
        return normalized


class SessionResponse(BaseModel):
    tenant_id: str
    user_id: str
    is_admin: bool = False


def set_auth_cookies(response: Response, tokens: AuthTokens, settings: Settings) -> None:
    common = {"secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        httponly=True,
        max_age=settings.access_token_minutes * 60,
        path="/",
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        httponly=True,
        max_age=settings.refresh_token_days * 86400,
        # The browser reaches auth through the public /api/auth proxy while
        # backend integration clients use /auth directly. A root-scoped,
        # HttpOnly refresh cookie supports both routes; CSRF validation still
        # protects every refresh and rotation request.
        path="/",
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        httponly=False,
        max_age=settings.refresh_token_days * 86400,
        path="/",
        **common,
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie(
        REFRESH_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax"
    )
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")


def create_auth_router(service: AuthService, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/login", response_model=SessionResponse)
    async def login(body: LoginRequest, response: Response, request: Request) -> SessionResponse:
        try:
            client_key = request.client.host if request.client else "unknown"
            tokens = await service.login(body.email, body.password, client_key=client_key)
            context = await service.validate_access(tokens.access_token)
        except LoginRateLimited as error:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "login temporarily blocked"
            ) from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from error
        set_auth_cookies(response, tokens, settings)
        return SessionResponse(
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
            is_admin=context.is_admin,
        )

    @router.get("/me", response_model=SessionResponse)
    async def me(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> SessionResponse:
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            context = await service.validate_access(access_token)
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error
        return SessionResponse(
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
            is_admin=context.is_admin,
        )

    @router.post("/refresh", response_model=SessionResponse)
    async def refresh(
        response: Response,
        refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> SessionResponse:
        if refresh_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token required")
        if csrf_header is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            tokens = await service.refresh(refresh_token, csrf_header)
            context = await service.validate_access(tokens.access_token)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except (AuthenticationFailed, RefreshTokenReuseDetected) as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh rejected") from error
        set_auth_cookies(response, tokens, settings)
        return SessionResponse(
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
            is_admin=context.is_admin,
        )

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        response: Response,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        if csrf_header is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            await service.logout(access_token, csrf_header)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error
        clear_auth_cookies(response, settings)

    return router
