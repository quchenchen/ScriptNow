from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Cookie, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from scriptflow_v7.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptflow_v7.platform.auth_api import ACCESS_COOKIE
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import ProjectModel
from scriptflow_v7.script.contracts import ScriptBlock
from scriptflow_v7.script.delivery import ScriptDeliveryError, ScriptExportService
from scriptflow_v7.script.domain import (
    BlueprintAnchorDraft,
    BlueprintDraft,
    ScriptBlueprintAnchorModel,
    ScriptBlueprintCandidateModel,
    ScriptBlueprintModel,
    ScriptDocumentRevisionModel,
    ScriptExportManifestModel,
    ScriptStoryCoreCandidateModel,
    ScriptStructureCandidateModel,
    StoryCoreDraft,
)
from scriptflow_v7.script.generator import ScriptCreativeGenerator, ScriptGenerationError
from scriptflow_v7.script.history import (
    ScriptHistoryConflict,
    ScriptHistoryError,
    ScriptHistoryService,
)
from scriptflow_v7.script.project import ScriptPlanModel, ScriptStoryMapModel
from scriptflow_v7.script.service import ScriptConflict, ScriptDomainError, ScriptService
from scriptflow_v7.script.story_map import Episode


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    feedback: str | None = None


class ProposeStoryCoresRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    drafts: tuple[StoryCoreDraft, ...] = Field(min_length=3, max_length=3)
    feedback: str | None = None


class ProposeBlueprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    anchors: tuple[BlueprintAnchorDraft, ...] = Field(min_length=1)
    feedback: str | None = None


class AdoptResponse(BaseModel):
    id: str
    status: str


class ProposeStoryMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    episodes: tuple[Episode, ...] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=120)


class ScriptSelectionEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: str
    element_id: str
    excerpt: str = Field(min_length=2, max_length=500)
    operation: Literal["expand", "shorten", "polish", "revise"]
    instruction: str = Field(default="", max_length=2_000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class ScriptStateResponse(BaseModel):
    phase: str
    script_format: str
    story_cores: list[dict[str, object]]
    blueprint: dict[str, object] | None
    blueprint_candidates: list[dict[str, object]]
    story_map: dict[str, object]
    story_map_candidates: list[dict[str, object]]
    documents: list[dict[str, object]]


class ScriptExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ids: tuple[str, ...] = Field(min_length=1)
    form: Literal["clean", "working"] = "clean"
    idempotency_key: str = Field(min_length=1, max_length=120)


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_current_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=120)


def create_script_router(database: Database, auth: AuthService, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/script/projects/{project_id}", tags=["script"])
    service = ScriptService(database)
    exports = ScriptExportService(database)
    history = ScriptHistoryService(database)
    generator = ScriptCreativeGenerator(database, settings)

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

    @router.get("/state", response_model=ScriptStateResponse)
    async def state(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> ScriptStateResponse:
        context = await read_context(access_token)
        try:
            return await _state(database, str(context.tenant_id), project_id)
        except ScriptDomainError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Script project not found") from error

    @router.post("/story-cores/generate", response_model=list[dict[str, object]])
    async def generate_story_cores(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[dict[str, object]]:
        context = await action_context(access_token, csrf_token)
        project = await _script_project(database, str(context.tenant_id), project_id)
        try:
            drafts = await generator.story_cores(
                tenant_id=str(context.tenant_id),
                project=project,
                feedback=body.feedback,
            )
        except ScriptGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        records = await service.generate_story_cores(
            tenant_id=str(context.tenant_id),
            project_id=project_id,
            drafts=drafts,
            revision_feedback=body.feedback,
            idempotency_key=body.idempotency_key,
        )
        return [_core(item) for item in records]

    @router.post("/story-cores/{candidate_id}/adopt", response_model=AdoptResponse)
    async def adopt_story_core(
        project_id: str,
        candidate_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        try:
            candidate = await service.adopt_story_core(
                tenant_id=str(context.tenant_id), project_id=project_id, candidate_id=candidate_id
            )
            return AdoptResponse(id=candidate.id, status="adopted")
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-cores/propose", response_model=list[dict[str, object]])
    async def propose_story_cores(
        project_id: str,
        body: ProposeStoryCoresRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[dict[str, object]]:
        context = await action_context(access_token, csrf_token)
        records = await service.generate_story_cores(
            tenant_id=str(context.tenant_id),
            project_id=project_id,
            drafts=body.drafts,
            revision_feedback=body.feedback,
            idempotency_key=body.idempotency_key,
        )
        return [_core(item) for item in records]

    @router.post("/blueprints/generate", response_model=AdoptResponse)
    async def generate_blueprint(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        project = await _script_project(database, str(context.tenant_id), project_id)
        current = await _state(database, str(context.tenant_id), project_id)
        adopted_core = next(
            (item for item in current.story_cores if item["status"] == "adopted"), None
        )
        if adopted_core is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "请先采纳一个创意方向")
        try:
            draft = await generator.blueprint(
                tenant_id=str(context.tenant_id),
                project=project,
                story_core=adopted_core,
                feedback=body.feedback,
            )
        except ScriptGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        try:
            candidate = await service.propose_blueprint(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                draft=draft,
                idempotency_key=body.idempotency_key,
                revision_feedback=body.feedback,
            )
            return AdoptResponse(id=candidate.id, status=str(candidate.status))
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/blueprints/{candidate_id}/adopt", response_model=AdoptResponse)
    async def adopt_blueprint(
        project_id: str,
        candidate_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        try:
            blueprint = await service.adopt_blueprint_candidate(
                tenant_id=str(context.tenant_id), project_id=project_id, candidate_id=candidate_id
            )
            return AdoptResponse(id=blueprint.id, status="adopted")
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/blueprints/propose", response_model=AdoptResponse)
    async def propose_blueprint(
        project_id: str,
        body: ProposeBlueprintRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        try:
            candidate = await service.propose_blueprint(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                draft=BlueprintDraft(anchors=body.anchors),
                idempotency_key=body.idempotency_key,
                revision_feedback=body.feedback,
            )
            return AdoptResponse(id=candidate.id, status=str(candidate.status))
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-map/generate", response_model=AdoptResponse)
    async def generate_story_map(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        project = await _script_project(database, str(context.tenant_id), project_id)
        current = await _state(database, str(context.tenant_id), project_id)
        version = int(current.story_map["version"])
        adopted_core = next(
            (item for item in current.story_cores if item["status"] == "adopted"), None
        )
        if adopted_core is None or current.blueprint is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "请先采纳创意方向和蓝图")
        try:
            episodes = await generator.story_map(
                tenant_id=str(context.tenant_id),
                project=project,
                story_core=adopted_core,
                anchors=list(current.blueprint["anchors"]),
                feedback=body.feedback,
            )
        except ScriptGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        try:
            candidate = await service.propose_structure(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                expected_version=version,
                episodes=episodes,
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=candidate.id, status=str(candidate.status))
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-map/propose", response_model=AdoptResponse)
    async def propose_story_map(
        project_id: str,
        body: ProposeStoryMapRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        try:
            candidate = await service.propose_structure(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                expected_version=body.expected_version,
                episodes=body.episodes,
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=candidate.id, status=str(candidate.status))
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-map/{candidate_id}/adopt", response_model=AdoptResponse)
    async def adopt_story_map(
        project_id: str,
        candidate_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        try:
            story_map = await service.adopt_structure(
                tenant_id=str(context.tenant_id), project_id=project_id, candidate_id=candidate_id
            )
            return AdoptResponse(id=story_map.id, status="adopted")
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/scenes/{scene_id}/generate", response_model=AdoptResponse)
    async def generate_scene(
        project_id: str,
        scene_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        context = await action_context(access_token, csrf_token)
        unique = uuid4().hex[:8]
        blocks = (
            ScriptBlock(para_id=f"{unique}-1", type="slugline", text="内景 核心地点 夜"),
            ScriptBlock(para_id=f"{unique}-2", type="action", text="核心人物进入现场。"),
            ScriptBlock(para_id=f"{unique}-3", type="character", text="核心人物"),
            ScriptBlock(para_id=f"{unique}-4", type="dialogue", text="事情从这里开始。"),
        )
        try:
            revision = await service.propose_document(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                scene_id=scene_id,
                blocks=blocks,
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=revision.id, status=str(revision.status))
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/scenes/{scene_id}/revisions/{revision_id}/adopt", response_model=AdoptResponse)
    async def adopt_scene(
        project_id: str,
        scene_id: str,
        revision_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        del scene_id
        context = await action_context(access_token, csrf_token)
        try:
            revision = await service.adopt_document(
                tenant_id=str(context.tenant_id), project_id=project_id, revision_id=revision_id
            )
            return AdoptResponse(id=revision.id, status="adopted")
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/scenes/{scene_id}/selection-edits")
    async def propose_selection_edit(
        project_id: str,
        scene_id: str,
        body: ScriptSelectionEditRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        await _script_project(database, str(context.tenant_id), project_id)
        async with database.session() as session:
            base = await session.get(ScriptDocumentRevisionModel, body.revision_id)
            if (
                base is None
                or base.project_id != project_id
                or base.scene_id != scene_id
                or str(base.status) != "adopted"
            ):
                raise HTTPException(status.HTTP_409_CONFLICT, "Script base revision is stale")
            blocks = [dict(item) for item in base.blocks]
        target = next((item for item in blocks if item.get("para_id") == body.element_id), None)
        if target is None or body.excerpt not in str(target.get("text", "")):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Script selection can no longer be located"
            )
        if target.get("type") not in {"action", "dialogue"}:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Script selection edits only support action and dialogue paragraphs",
            )
        before = str(target["text"])
        selected = body.excerpt
        transformed = {
            "expand": f"{selected} 他停了一瞬，才继续完成这个动作。",
            "shorten": selected[: max(2, len(selected) // 2)].rstrip("，。") + "。",
            "polish": f"{selected.rstrip('。')}，动作干净，却藏着迟疑。",
            "revise": f"{selected.rstrip('。')}，但这一刻改变了他的下一步选择。",
        }[body.operation]
        target["text"] = before.replace(selected, transformed, 1)
        try:
            candidate = await service.propose_document(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                scene_id=scene_id,
                blocks=tuple(ScriptBlock.model_validate(item) for item in blocks),
                idempotency_key=body.idempotency_key,
            )
        except (ScriptConflict, ScriptDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "id": candidate.id,
            "medium": "script",
            "unit_id": scene_id,
            "base_revision_id": body.revision_id,
            "element_id": body.element_id,
            "operation": body.operation,
            "excerpt": body.excerpt,
            "status": str(candidate.status),
            "diff": {"before": before, "after": target["text"]},
            "instruction": body.instruction,
        }

    @router.get("/exports/options")
    async def export_options(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        context = await read_context(access_token)
        try:
            return await exports.options(tenant_id=str(context.tenant_id), project_id=project_id)
        except ScriptDeliveryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/exports")
    async def create_export(
        project_id: str,
        body: ScriptExportRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        try:
            manifest = await exports.export(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                scene_ids=body.scene_ids,
                form=body.form,
                idempotency_key=body.idempotency_key,
            )
        except ScriptDeliveryError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return _script_export(manifest)

    @router.get("/exports/{manifest_id}/download")
    async def download_export(
        project_id: str,
        manifest_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> Response:
        context = await read_context(access_token)
        await _script_project(database, str(context.tenant_id), project_id)
        async with database.session() as session:
            manifest = await session.get(ScriptExportManifestModel, manifest_id)
            if manifest is None or manifest.project_id != project_id or manifest.artifact is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Script export is unavailable")
            return Response(
                content=manifest.artifact,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="script-{manifest.id}.docx"'
                },
            )

    @router.post("/snapshots", status_code=status.HTTP_201_CREATED)
    async def create_snapshot(
        project_id: str,
        body: SnapshotRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        try:
            return _snapshot_view(
                await history.create_snapshot(
                    tenant_id=str(context.tenant_id), project_id=project_id, name=body.name
                )
            )
        except ScriptHistoryError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/snapshots")
    async def list_snapshots(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        context = await read_context(access_token)
        try:
            return [
                _snapshot_view(item)
                for item in await history.list(
                    tenant_id=str(context.tenant_id), project_id=project_id
                )
            ]
        except ScriptHistoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.get("/snapshots/{snapshot_id}/diff")
    async def snapshot_diff(
        project_id: str,
        snapshot_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        context = await read_context(access_token)
        try:
            return await history.diff(
                tenant_id=str(context.tenant_id), project_id=project_id, snapshot_id=snapshot_id
            )
        except ScriptHistoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/snapshots/{snapshot_id}/rollback")
    async def rollback_snapshot(
        project_id: str,
        snapshot_id: str,
        body: RollbackRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        context = await action_context(access_token, csrf_token)
        try:
            revisions = await history.rollback(
                tenant_id=str(context.tenant_id),
                project_id=project_id,
                snapshot_id=snapshot_id,
                expected_current_hash=body.expected_current_hash,
                idempotency_key=body.idempotency_key,
            )
            return {"snapshot_id": snapshot_id, "revision_ids": [item.id for item in revisions]}
        except ScriptHistoryConflict as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except ScriptHistoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    return router


def _script_export(item: ScriptExportManifestModel) -> dict[str, object]:
    return {
        "id": item.id,
        "status": str(item.status),
        "scope": item.scope,
        "form": item.form,
        "script_format": item.script_format,
        "sha256": item.artifact_sha256,
        "byte_size": item.byte_size,
        "attempts": item.attempts,
        "error": item.error,
    }


def _snapshot_view(item) -> dict[str, object]:
    return {
        "id": item.id,
        "version": item.version,
        "name": item.name,
        "scope": item.scope,
        "word_count": item.word_count,
        "content_hash": item.content_hash,
        "base_snapshot_id": item.base_snapshot_id,
        "created_at": item.created_at.isoformat(),
    }


async def _script_project(database: Database, tenant_id: str, project_id: str) -> ProjectModel:
    async with database.session() as session:
        project = await session.get(ProjectModel, project_id)
        if project is None or project.tenant_id != tenant_id or project.medium != "script":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Script project not found")
        return project


async def _state(database: Database, tenant_id: str, project_id: str) -> ScriptStateResponse:
    await _script_project(database, tenant_id, project_id)
    async with database.session() as session:
        plan = (
            await session.scalars(
                select(ScriptPlanModel).where(ScriptPlanModel.project_id == project_id)
            )
        ).one()
        cores = list(
            await session.scalars(
                select(ScriptStoryCoreCandidateModel)
                .where(ScriptStoryCoreCandidateModel.project_id == project_id)
                .order_by(
                    ScriptStoryCoreCandidateModel.generation,
                    ScriptStoryCoreCandidateModel.ordinal,
                )
            )
        )
        blueprint = (
            await session.scalars(
                select(ScriptBlueprintModel).where(
                    ScriptBlueprintModel.project_id == project_id,
                    ScriptBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        blueprint_candidates = list(
            await session.scalars(
                select(ScriptBlueprintCandidateModel)
                .where(ScriptBlueprintCandidateModel.project_id == project_id)
                .order_by(ScriptBlueprintCandidateModel.id.desc())
            )
        )
        anchors = []
        if blueprint:
            anchors = list(
                await session.scalars(
                    select(ScriptBlueprintAnchorModel).where(
                        ScriptBlueprintAnchorModel.blueprint_id == blueprint.id
                    )
                )
            )
        story_map = (
            await session.scalars(
                select(ScriptStoryMapModel).where(ScriptStoryMapModel.project_id == project_id)
            )
        ).one()
        story_map_candidates = list(
            await session.scalars(
                select(ScriptStructureCandidateModel)
                .where(ScriptStructureCandidateModel.project_id == project_id)
                .order_by(ScriptStructureCandidateModel.id.desc())
            )
        )
        documents = list(
            await session.scalars(
                select(ScriptDocumentRevisionModel)
                .where(ScriptDocumentRevisionModel.project_id == project_id)
                .order_by(
                    ScriptDocumentRevisionModel.scene_id,
                    ScriptDocumentRevisionModel.revision_number,
                )
            )
        )
        return ScriptStateResponse(
            phase=plan.status,
            script_format=str(plan.direction.get("script_format") or ""),
            story_cores=[_core(item) for item in cores],
            blueprint=(
                {
                    "id": blueprint.id,
                    "version": blueprint.version,
                    "anchors": [
                        {
                            "id": item.anchor_key,
                            "kind": item.kind,
                            "name": item.name,
                            "payload": item.payload,
                        }
                        for item in anchors
                    ],
                }
                if blueprint
                else None
            ),
            blueprint_candidates=[
                {"id": item.id, "status": str(item.status), "anchors": item.draft["anchors"]}
                for item in blueprint_candidates
            ],
            story_map={
                "id": story_map.id,
                "version": story_map.version,
                "episodes": story_map.episodes,
            },
            story_map_candidates=[
                {
                    "id": item.id,
                    "status": str(item.status),
                    "base_version": item.base_version,
                    "episodes": item.proposed_episodes,
                    "impact": item.impact,
                }
                for item in story_map_candidates
            ],
            documents=[
                {
                    "id": item.id,
                    "scene_id": item.scene_id,
                    "revision_number": item.revision_number,
                    "base_revision_id": item.base_revision_id,
                    "blocks": item.blocks,
                    "status": str(item.status),
                }
                for item in documents
            ],
        )


def _core(item: ScriptStoryCoreCandidateModel) -> dict[str, object]:
    return {
        "id": item.id,
        "generation": item.generation,
        "ordinal": item.ordinal,
        "title": item.title,
        "concept": item.concept,
        "angles": item.angles,
        "details": item.details,
        "status": str(item.status),
        "revision_feedback": item.revision_feedback,
    }
