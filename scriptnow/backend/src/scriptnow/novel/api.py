from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from scriptnow.novel.blueprint import NovelBlueprintError, NovelBlueprintGenerator
from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.creative_graph import (
    CreativeGraphExtractor,
    CreativeGraphQueue,
    _ExtractionJob,
    read_creative_graph,
)
from scriptnow.novel.delivery import NovelDeliveryError, NovelExportService
from scriptnow.novel.domain import (
    NovelBlueprintAnchorDraft,
    NovelBlueprintAnchorModel,
    NovelBlueprintCandidateModel,
    NovelBlueprintDraft,
    NovelBlueprintModel,
    NovelDocumentRevisionModel,
    NovelExportManifestModel,
    NovelQualityReportModel,
    NovelStoryCoreCandidateModel,
    NovelStoryCoreDraft,
    NovelStructureCandidateModel,
)
from scriptnow.novel.history import NovelHistoryConflict, NovelHistoryError, NovelHistoryService
from scriptnow.novel.ideation import NovelIdeationError, NovelIdeationGenerator
from scriptnow.novel.project import NovelPlanModel, NovelStoryMapModel
from scriptnow.novel.quality import (
    NovelQualityError,
    NovelQualityService,
)
from scriptnow.novel.quality_evaluator import NovelQualityEvaluator
from scriptnow.novel.service import NovelConflict, NovelDomainError, NovelService
from scriptnow.novel.story_map import Volume
from scriptnow.novel.story_map_generator import (
    NovelStoryMapGenerationError,
    NovelStoryMapGenerator,
)
from scriptnow.novel.writer import NovelChapterGenerator, NovelWriterError
from scriptnow.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel
from scriptnow.platform.translation import FaithfulTranslationService


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    feedback: str | None = None
    source_revision_id: str | None = None


class ProposeStoryCoresRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    drafts: tuple[NovelStoryCoreDraft, ...] = Field(min_length=3, max_length=3)
    feedback: str | None = Field(default=None, max_length=2_000)


class ProposeBlueprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    anchors: tuple[NovelBlueprintAnchorDraft, ...] = Field(min_length=1)


class ProposeChapterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    blocks: tuple[NovelBlock, ...] = Field(min_length=1)


class ManualChapterRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120)
    blocks: tuple[NovelBlock, ...] = Field(min_length=1)


class GenerateNovelQualityReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: str
    idempotency_key: str = Field(min_length=1, max_length=120)


class AdoptResponse(BaseModel):
    id: str
    status: str


class ProposeStoryMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    volumes: tuple[Volume, ...] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=120)


class NovelSelectionEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: str
    element_id: str
    excerpt: str = Field(min_length=2, max_length=500)
    operation: Literal["expand", "shorten", "polish", "revise"]
    instruction: str = Field(default="", max_length=2_000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class NovelStateResponse(BaseModel):
    phase: str
    creative_language: str
    creation_settings: dict[str, object]
    story_cores: list[dict[str, object]]
    blueprint: dict[str, object] | None
    blueprint_candidates: list[dict[str, object]]
    story_map: dict[str, object]
    story_map_candidates: list[dict[str, object]]
    documents: list[dict[str, object]]


class NovelExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_ids: tuple[str, ...] = Field(min_length=1)
    form: Literal["clean", "working"] = "clean"
    translation_mode: Literal["none", "faithful"] = "none"
    target_language: str | None = Field(default=None, min_length=2, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=120)


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_current_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=120)


def create_novel_router(database: Database, auth: AuthService, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/novel/projects/{project_id}", tags=["novel"])
    service = NovelService(database)
    exports = NovelExportService(
        database, translator=FaithfulTranslationService(database, settings)
    )
    history = NovelHistoryService(database)
    ideation = NovelIdeationGenerator(database, settings)
    story_map_generator = NovelStoryMapGenerator(database, settings)
    writer = NovelChapterGenerator(database, settings)
    quality = NovelQualityService(database)
    creative_graph = CreativeGraphExtractor(database, settings)
    graph_queue = CreativeGraphQueue()
    graph_queue.attach(creative_graph)
    quality_evaluator = NovelQualityEvaluator(database, settings)

    async def context(access_token: str | None, csrf_token: str | None = None, *, write=False):
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

    @router.get("/state", response_model=NovelStateResponse)
    async def state(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> NovelStateResponse:
        auth_context = await context(access_token)
        return await _state(database, str(auth_context.tenant_id), project_id)

    @router.post("/story-cores/generate", response_model=list[dict[str, object]])
    async def generate_story_cores(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[dict[str, object]]:
        auth_context = await context(access_token, csrf_token, write=True)
        project = await _novel_project(database, str(auth_context.tenant_id), project_id)
        try:
            drafts = await ideation.generate(
                tenant_id=str(auth_context.tenant_id),
                project=project,
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            records = await service.generate_story_cores(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                drafts=drafts,
                idempotency_key=body.idempotency_key,
                revision_feedback=body.feedback,
            )
            return [_core(item) for item in records]
        except NovelIdeationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-cores/{candidate_id}/adopt", response_model=AdoptResponse)
    async def adopt_story_core(
        project_id: str,
        candidate_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.adopt_story_core(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                candidate_id=candidate_id,
            )
            return AdoptResponse(id=item.id, status="adopted")
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-cores/propose", response_model=list[dict[str, object]])
    async def propose_story_cores(
        project_id: str,
        body: ProposeStoryCoresRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> list[dict[str, object]]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            records = await service.generate_story_cores(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                drafts=body.drafts,
                idempotency_key=body.idempotency_key,
                revision_feedback=body.feedback,
            )
            return [_core(item) for item in records]
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/blueprints/generate", response_model=AdoptResponse)
    async def generate_blueprint(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            async with database.session() as session:
                project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != str(auth_context.tenant_id):
                raise NovelConflict("project not found")
            draft = await NovelBlueprintGenerator(database, settings).generate(
                tenant_id=str(auth_context.tenant_id),
                project=project,
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            item = await service.propose_blueprint(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                draft=draft,
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except NovelBlueprintError as error:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "蓝图格式需要整理，当前内容已保留，请重新生成一次。",
            ) from error
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/blueprints/{candidate_id}/adopt", response_model=AdoptResponse)
    async def adopt_blueprint(
        project_id: str,
        candidate_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.adopt_blueprint(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                candidate_id=candidate_id,
            )
            return AdoptResponse(id=item.id, status="adopted")
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/blueprints/propose", response_model=AdoptResponse)
    async def propose_blueprint(
        project_id: str,
        body: ProposeBlueprintRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.propose_blueprint(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                draft=NovelBlueprintDraft(anchors=body.anchors),
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-map/generate", response_model=AdoptResponse)
    async def generate_story_map(
        project_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        current = await _state(database, str(auth_context.tenant_id), project_id)
        try:
            project = await _novel_project(
                database, str(auth_context.tenant_id), project_id
            )
            volumes = await story_map_generator.generate(
                tenant_id=str(auth_context.tenant_id),
                project=project,
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
            )
            item = await service.propose_structure(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                expected_version=int(current.story_map["version"]),
                volumes=volumes,
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except NovelStoryMapGenerationError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-map/propose", response_model=AdoptResponse)
    async def propose_story_map(
        project_id: str,
        body: ProposeStoryMapRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.propose_structure(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                expected_version=body.expected_version,
                volumes=body.volumes,
                idempotency_key=body.idempotency_key,
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/story-map/{candidate_id}/adopt", response_model=AdoptResponse)
    async def adopt_story_map(
        project_id: str,
        candidate_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.adopt_structure(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                candidate_id=candidate_id,
            )
            return AdoptResponse(id=item.id, status="adopted")
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/chapters/{chapter_id}/generate", response_model=AdoptResponse)
    async def generate_chapter(
        project_id: str,
        chapter_id: str,
        body: GenerateRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            async with database.session() as session:
                project = await session.get(ProjectModel, project_id)
                if project is None or project.tenant_id != str(auth_context.tenant_id):
                    raise NovelDomainError("project does not exist")
            blocks = await writer.generate(
                tenant_id=str(auth_context.tenant_id),
                project=project,
                chapter_id=chapter_id,
                idempotency_key=body.idempotency_key,
                feedback=body.feedback,
                source_revision_id=body.source_revision_id,
            )
            item = await service.propose_document(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                chapter_id=chapter_id,
                blocks=blocks,
                idempotency_key=body.idempotency_key,
                source="agent",
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except (NovelConflict, NovelDomainError, NovelWriterError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/chapters/{chapter_id}/propose", response_model=AdoptResponse)
    async def propose_chapter(
        project_id: str,
        chapter_id: str,
        body: ProposeChapterRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.propose_document(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                chapter_id=chapter_id,
                blocks=body.blocks,
                idempotency_key=body.idempotency_key,
                source="human",
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post(
        "/chapters/{chapter_id}/revisions/{revision_id}/manual",
        response_model=AdoptResponse,
    )
    async def create_manual_chapter_revision(
        project_id: str,
        chapter_id: str,
        revision_id: str,
        body: ManualChapterRevisionRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.propose_document(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                chapter_id=chapter_id,
                blocks=body.blocks,
                idempotency_key=body.idempotency_key,
                parent_revision_id=revision_id,
                source="human",
            )
            return AdoptResponse(id=item.id, status=str(item.status))
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post(
        "/chapters/{chapter_id}/revisions/{revision_id}/adopt", response_model=AdoptResponse
    )
    async def adopt_chapter(
        project_id: str,
        chapter_id: str,
        revision_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> AdoptResponse:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            item = await service.adopt_document(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                revision_id=revision_id,
            )
            # Trigger creative graph extraction in background
            import asyncio
            chapter = next(
                (b for b in list(item.blocks) if isinstance(b, dict) and b.get("type") == "heading"),
                None,
            )
            chapter_title = str(chapter.get("text", "")) if chapter else chapter_id
            blocks = [dict(b) if isinstance(b, dict) else {"type": "prose", "text": str(b)} for b in list(item.blocks)]
            asyncio.create_task(
                creative_graph.extract_chapter(
                    tenant_id=str(auth_context.tenant_id),
                    project_id=project_id,
                    chapter_id=item.chapter_id,
                    chapter_title=chapter_title,
                    blocks=blocks,
                    idempotency_key=f"adopt:{revision_id}",
                )
            )
            return AdoptResponse(id=item.id, status="adopted")
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/chapters/{chapter_id}/quality-reports/generate")
    async def generate_quality_report(
        project_id: str,
        chapter_id: str,
        body: GenerateNovelQualityReportRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        project = await _novel_project(database, str(auth_context.tenant_id), project_id)
        try:
            item = await quality_evaluator.evaluate(
                tenant_id=str(auth_context.tenant_id),
                project=project,
                chapter_id=chapter_id,
                revision_id=body.revision_id,
                idempotency_key=body.idempotency_key,
            )
            return _quality_report(item)
        except NovelQualityError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/chapters/{chapter_id}/quality-reports")
    async def quality_report_history(
        project_id: str,
        chapter_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        auth_context = await context(access_token)
        try:
            items = await quality.history(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                chapter_id=chapter_id,
            )
            return [_quality_report(item) for item in items]
        except NovelQualityError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/chapters/{chapter_id}/selection-edits")
    async def propose_selection_edit(
        project_id: str,
        chapter_id: str,
        body: NovelSelectionEditRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        await _novel_project(database, str(auth_context.tenant_id), project_id)
        async with database.session() as session:
            base = await session.get(NovelDocumentRevisionModel, body.revision_id)
            if (
                base is None
                or base.project_id != project_id
                or base.chapter_id != chapter_id
                or str(base.status) != "adopted"
            ):
                raise HTTPException(status.HTTP_409_CONFLICT, "Novel base revision is stale")
            blocks = [dict(item) for item in base.blocks]
        target = next((item for item in blocks if item.get("block_id") == body.element_id), None)
        if target is None or body.excerpt not in str(target.get("text", "")):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Novel selection can no longer be located"
            )
        if target.get("type") not in {"prose", "dialogue", "quote"}:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Novel selection edits only support prose, dialogue and quote blocks",
            )
        before = str(target["text"])
        selected = body.excerpt
        transformed = {
            "expand": f"{selected} 她停下来，让这个念头在呼吸之间显出更深的来处。",
            "shorten": selected[: max(2, len(selected) // 2)].rstrip("，。") + "。",
            "polish": f"{selected.rstrip('。')}，余意像窗上的雨痕一样缓慢洇开。",
            "revise": f"{selected.rstrip('。')}，她却在念头落定前改变了理解它的方式。",
        }[body.operation]
        target["text"] = before.replace(selected, transformed, 1)
        try:
            candidate = await service.propose_document(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                chapter_id=chapter_id,
                blocks=tuple(NovelBlock.model_validate(item) for item in blocks),
                idempotency_key=body.idempotency_key,
            )
        except (NovelConflict, NovelDomainError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "id": candidate.id,
            "medium": "novel",
            "unit_id": chapter_id,
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
        auth_context = await context(access_token)
        try:
            return await exports.options(
                tenant_id=str(auth_context.tenant_id), project_id=project_id
            )
        except NovelDeliveryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/exports")
    async def create_export(
        project_id: str,
        body: NovelExportRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            manifest = await exports.export(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                chapter_ids=body.chapter_ids,
                form=body.form,
                translation_mode=body.translation_mode,
                target_language=body.target_language,
                idempotency_key=body.idempotency_key,
            )
        except NovelDeliveryError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return _novel_export(manifest)

    @router.get("/exports/{manifest_id}/download")
    async def download_export(
        project_id: str,
        manifest_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> Response:
        auth_context = await context(access_token)
        await _novel_project(database, str(auth_context.tenant_id), project_id)
        async with database.session() as session:
            manifest = await session.get(NovelExportManifestModel, manifest_id)
            if manifest is None or manifest.project_id != project_id or manifest.artifact is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel export is unavailable")
            return Response(
                content=manifest.artifact,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="novel-{manifest.id}.docx"'},
            )

    @router.post("/snapshots", status_code=status.HTTP_201_CREATED)
    async def create_snapshot(
        project_id: str,
        body: SnapshotRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            return _snapshot_view(
                await history.create_snapshot(
                    tenant_id=str(auth_context.tenant_id), project_id=project_id, name=body.name
                )
            )
        except NovelHistoryError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.get("/snapshots")
    async def list_snapshots(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> list[dict[str, object]]:
        auth_context = await context(access_token)
        try:
            return [
                _snapshot_view(item)
                for item in await history.list(
                    tenant_id=str(auth_context.tenant_id), project_id=project_id
                )
            ]
        except NovelHistoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.get("/snapshots/{snapshot_id}/diff")
    async def snapshot_diff(
        project_id: str,
        snapshot_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token)
        try:
            return await history.diff(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                snapshot_id=snapshot_id,
            )
        except NovelHistoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.post("/snapshots/{snapshot_id}/rollback")
    async def rollback_snapshot(
        project_id: str,
        snapshot_id: str,
        body: RollbackRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        auth_context = await context(access_token, csrf_token, write=True)
        try:
            revisions = await history.rollback(
                tenant_id=str(auth_context.tenant_id),
                project_id=project_id,
                snapshot_id=snapshot_id,
                expected_current_hash=body.expected_current_hash,
                idempotency_key=body.idempotency_key,
            )
            return {"snapshot_id": snapshot_id, "revision_ids": [item.id for item in revisions]}
        except NovelHistoryConflict as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except NovelHistoryError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @router.get("/creative-graph")
    async def creative_graph_data(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        await context(access_token)
        data = await read_creative_graph(database, project_id=project_id)
        # If graph is empty but chapters have been adopted, enqueue background extraction (once)
        if not data["chapters"] and not graph_queue._running and not graph_queue._jobs:
            async with database.session() as session:
                from sqlalchemy import select as sa_select

                from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
                adopted = list(
                    await session.scalars(
                        sa_select(NovelDocumentRevisionModel).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                        )
                    )
                )
            if adopted:
                tenant_id = str((await auth.validate_access(access_token)).tenant_id)
                for rev in adopted:
                    chapter = next(
                        (b for b in list(rev.blocks) if isinstance(b, dict) and b.get("type") == "heading"),
                        None,
                    )
                    chapter_title = str(chapter.get("text", "")) if chapter else rev.chapter_id
                    blocks = [dict(b) if isinstance(b, dict) else {"type": "prose", "text": str(b)} for b in list(rev.blocks)]
                    graph_queue.enqueue(_ExtractionJob(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        chapter_id=rev.chapter_id,
                        chapter_title=chapter_title,
                        blocks=blocks,
                        idempotency_key=f"lazy:{rev.id}",
                    ))
                return {
                    "status": "not_built",
                    "extraction_status": "running",
                    "chapters": [],
                    "nodes": [],
                    "edges": [],
                }
                extraction = "running" if (graph_queue._running or graph_queue._jobs) else ("ready" if data["chapters"] else "not_built")
        return {
            "status": "ready" if data["chapters"] else "not_built",
            "extraction_status": extraction,
            "chapters": [
                {"id": ch["chapter_key"], "type": "chapter", "label": ch["title"]}
                for ch in data["chapters"]
            ],
            "nodes": data["nodes"],
            "edges": data["edges"],
        }

    return router


def _novel_export(item: NovelExportManifestModel) -> dict[str, object]:
    return {
        "id": item.id,
        "status": str(item.status),
        "scope": item.scope,
        "form": item.form,
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


async def _novel_project(database: Database, tenant_id: str, project_id: str) -> ProjectModel:
    async with database.session() as session:
        project = await session.get(ProjectModel, project_id)
        if project is None or project.tenant_id != tenant_id or project.medium != "novel":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel project not found")
        return project


async def _state(database: Database, tenant_id: str, project_id: str) -> NovelStateResponse:
    project = await _novel_project(database, tenant_id, project_id)
    async with database.session() as session:
        plan = (
            await session.scalars(
                select(NovelPlanModel).where(NovelPlanModel.project_id == project_id)
            )
        ).one()
        cores = list(
            await session.scalars(
                select(NovelStoryCoreCandidateModel)
                .where(NovelStoryCoreCandidateModel.project_id == project_id)
                .order_by(
                    NovelStoryCoreCandidateModel.generation, NovelStoryCoreCandidateModel.ordinal
                )
            )
        )
        blueprint = (
            await session.scalars(
                select(NovelBlueprintModel).where(
                    NovelBlueprintModel.project_id == project_id,
                    NovelBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        blueprint_candidates = list(
            await session.scalars(
                select(NovelBlueprintCandidateModel)
                .where(NovelBlueprintCandidateModel.project_id == project_id)
                .order_by(NovelBlueprintCandidateModel.id.desc())
            )
        )
        anchors = (
            list(
                await session.scalars(
                    select(NovelBlueprintAnchorModel).where(
                        NovelBlueprintAnchorModel.blueprint_id == blueprint.id
                    )
                )
            )
            if blueprint
            else []
        )
        story_map = (
            await session.scalars(
                select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project_id)
            )
        ).one()
        story_map_candidates = list(
            await session.scalars(
                select(NovelStructureCandidateModel)
                .where(NovelStructureCandidateModel.project_id == project_id)
                .order_by(NovelStructureCandidateModel.id.desc())
            )
        )
        documents = list(
            await session.scalars(
                select(NovelDocumentRevisionModel)
                .where(NovelDocumentRevisionModel.project_id == project_id)
                .order_by(
                    NovelDocumentRevisionModel.chapter_id,
                    NovelDocumentRevisionModel.revision_number,
                )
            )
        )
        return NovelStateResponse(
            phase=plan.status,
            creative_language=str(project.direction.get("language") or ""),
            creation_settings={
                "chapter_target_words": project.direction.get("chapter_target_words"),
                "volume_count": project.direction.get("volume_one"),
                "chapters_per_volume": project.direction.get("volume_two"),
            },
            story_cores=[_core(item) for item in cores],
            blueprint={
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
            else None,
            blueprint_candidates=[
                {"id": item.id, "status": str(item.status), "anchors": item.draft["anchors"]}
                for item in blueprint_candidates
            ],
            story_map={
                "id": story_map.id,
                "version": story_map.version,
                "volumes": story_map.volumes,
            },
            story_map_candidates=[
                {
                    "id": item.id,
                    "status": str(item.status),
                    "base_version": item.base_version,
                    "volumes": item.proposed_volumes,
                    "impact": item.impact,
                }
                for item in story_map_candidates
            ],
            documents=[
                {
                    "id": item.id,
                    "chapter_id": item.chapter_id,
                    "revision_number": item.revision_number,
                    "base_revision_id": item.base_revision_id,
                    "parent_revision_id": item.parent_revision_id,
                    "source": item.source,
                    "blocks": item.blocks,
                    "status": str(item.status),
                }
                for item in documents
            ],
        )


def _core(item: NovelStoryCoreCandidateModel) -> dict[str, object]:
    return {
        "id": item.id,
        "generation": item.generation,
        "ordinal": item.ordinal,
        "title": item.title,
        "premise": item.premise,
        "point_of_view": item.point_of_view,
        "narrative_constraints": item.narrative_constraints,
        "angles": item.angles,
        "status": str(item.status),
        "revision_feedback": item.revision_feedback,
    }


def _quality_report(item: NovelQualityReportModel) -> dict[str, object]:
    return {
        "id": item.id,
        "chapter_id": item.chapter_id,
        "revision_id": item.revision_id,
        "rubric_version": item.rubric_version,
        "source_profile_version": item.source_profile_version,
        "skill_plan_fingerprint": item.skill_plan_fingerprint,
        "dimensions": item.dimensions,
        "overall_status": item.overall_status,
        "maturity_score": item.maturity_score,
        "summary": item.summary,
        "author": item.author,
        "created_at": item.created_at.isoformat(),
    }
