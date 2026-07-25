from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CoverArtifactModel,
    ImageModelModel,
    ProjectModel,
    ProviderModel,
    TenantModel,
    TierModel,
    WorkPackageModel,
)
from scriptnow.work_package.service import (
    COVER_OUTPUT_SPECS,
    DEFAULT_COVER_OUTPUTS,
    WorkPackageError,
    WorkPackageService,
)


class GeneratePackageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    feedback: str | None = Field(default=None, max_length=2_000)


class GenerateCoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_model_id: str = Field(min_length=1, max_length=36)
    output_keys: tuple[str, ...] = Field(default=DEFAULT_COVER_OUTPUTS, min_length=1, max_length=5)
    prompt: str | None = Field(default=None, min_length=1, max_length=20_000)


class PackageResponse(BaseModel):
    id: str
    version: int
    title: str
    synopsis: str
    tags: list[str]
    language: str
    cover_brief: dict[str, object]
    cover_prompt: str


class CoverResponse(BaseModel):
    id: str
    work_package_id: str
    image_model_id: str
    image_url: str
    platform_key: str
    width: int
    height: int
    language: str
    status: str


class CoverOutputSpecResponse(BaseModel):
    key: str
    platform: str
    width: int
    height: int
    ratio: str
    formats: tuple[str, ...]
    max_bytes: int | None
    note: str
    default: bool


class CreatorImageModelResponse(BaseModel):
    id: str
    key: str
    display_name: str
    provider_name: str
    available: bool
    reason: str | None = None


def _package(value: WorkPackageModel) -> PackageResponse:
    return PackageResponse(
        id=value.id,
        version=value.version,
        title=value.title,
        synopsis=value.synopsis,
        tags=value.tags,
        language=value.language,
        cover_brief=value.cover_brief,
        cover_prompt=value.cover_prompt,
    )


def _cover(value: CoverArtifactModel) -> CoverResponse:
    return CoverResponse(
        id=value.id,
        work_package_id=value.work_package_id,
        image_model_id=value.image_model_id,
        image_url=value.image_url,
        platform_key=value.platform_key,
        width=value.width,
        height=value.height,
        language=value.language,
        status=value.status,
    )


def create_work_package_router(
    database: Database, auth: AuthService, settings: Settings
) -> APIRouter:
    router = APIRouter(prefix="/projects/{project_id}/packaging", tags=["packaging"])
    service = WorkPackageService(database, settings)

    @router.get("/cover-output-specs", response_model=list[CoverOutputSpecResponse])
    async def cover_output_specs() -> list[CoverOutputSpecResponse]:
        return [
            CoverOutputSpecResponse(
                key=item.key,
                platform=item.platform,
                width=item.width,
                height=item.height,
                ratio=item.ratio,
                formats=item.formats,
                max_bytes=item.max_bytes,
                note=item.note,
                default=item.key in DEFAULT_COVER_OUTPUTS,
            )
            for item in COVER_OUTPUT_SPECS.values()
        ]

    async def context(
        access_token: str | None, csrf_token: str | None = None, *, write: bool = False
    ):
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        if write and csrf_token is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            if write:
                return await auth.authorize_action(access_token, csrf_token)
            return await auth.validate_access(access_token)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    @router.get("/image-models", response_model=list[CreatorImageModelResponse])
    async def image_models(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[CreatorImageModelResponse]:
        auth_context = await context(access_token)
        async with database.session() as session:
            tenant = await session.get(TenantModel, str(auth_context.tenant_id))
            project = await session.get(ProjectModel, project_id)
            if tenant is None or project is None or project.tenant_id != tenant.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
            current_tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
            ).one_or_none()
            rows = (
                await session.execute(
                    select(ImageModelModel, ProviderModel, TierModel)
                    .join(ProviderModel, ProviderModel.id == ImageModelModel.provider_id)
                    .join(TierModel, TierModel.id == ImageModelModel.min_tier_id)
                    .order_by(ImageModelModel.display_name)
                )
            ).all()
            response: list[CreatorImageModelResponse] = []
            for model, provider, minimum in rows:
                reason = None
                if not model.enabled:
                    reason = "disabled"
                elif (
                    provider.credential_ciphertext is None
                    or provider.credential_nonce is None
                    or provider.credential_key_version is None
                    or not provider.base_url
                ):
                    reason = "provider_unavailable"
                elif current_tier is None or current_tier.rank < minimum.rank:
                    reason = "upgrade_required"
                response.append(
                    CreatorImageModelResponse(
                        id=model.id,
                        key=model.key,
                        display_name=model.display_name,
                        provider_name=provider.name,
                        available=reason is None,
                        reason=reason,
                    )
                )
            return response

    @router.get("", response_model=PackageResponse | None)
    async def latest(
        project_id: str, access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None
    ) -> PackageResponse | None:
        auth_context = await context(access_token)
        value = await service.latest(tenant_id=str(auth_context.tenant_id), project_id=project_id)
        return _package(value) if value else None

    @router.get("/covers", response_model=list[CoverResponse])
    async def covers(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[CoverResponse]:
        auth_context = await context(access_token)
        return [
            _cover(item)
            for item in await service.covers(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
            )
        ]

    @router.post("/generate", response_model=PackageResponse)
    async def generate(
        project_id: str,
        body: GeneratePackageRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> PackageResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            return _package(
                await service.generate(
                    tenant_id=str(auth_context.tenant_id),
                    project_id=project_id,
                    idempotency_key=body.idempotency_key,
                    feedback=body.feedback,
                )
            )
        except WorkPackageError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/covers/generate", response_model=list[CoverResponse])
    async def generate_cover(
        project_id: str,
        body: GenerateCoverRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[CoverResponse]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            return [
                _cover(item)
                for item in await service.generate_covers(
                    tenant_id=str(auth_context.tenant_id),
                    project_id=project_id,
                    image_model_id=body.image_model_id,
                    output_keys=body.output_keys,
                    prompt_override=body.prompt,
                )
            ]
        except WorkPackageError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.delete("/covers/{cover_id}", status_code=204)
    async def delete_cover(
        project_id: str,
        cover_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ):
        auth_context = await context(access_token, csrf_token, write=True)
        async with database.session() as session:
            cover = await session.get(CoverArtifactModel, cover_id)
            if cover is None or cover.project_id != project_id or cover.tenant_id != str(auth_context.tenant_id):
                raise HTTPException(404, "cover not found")
            # Delete local file if exists
            import os as _os
            url = cover.image_url or ""
            if url.startswith("/files/covers/"):
                rel = url.replace("/files/covers/", "")
                local = _os.path.join(settings.workspace_root, "covers", rel)
                try:
                    _os.remove(local)
                except OSError:
                    pass
            await session.delete(cover)
            await session.flush()
        return None

    return router
