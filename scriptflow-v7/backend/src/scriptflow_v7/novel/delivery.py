import hashlib
from collections.abc import Callable

from sqlalchemy import func, select

from scriptflow_v7.novel.contracts import NovelBlock
from scriptflow_v7.novel.domain import (
    NovelDocumentRevisionModel,
    NovelExportManifestModel,
    NovelRevisionStatus,
)
from scriptflow_v7.novel.export import NovelExportChapter, render_novel_docx
from scriptflow_v7.novel.project import NovelStoryMapModel
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import DeliveryStatus, ProjectEventModel, ProjectModel


class NovelDeliveryError(RuntimeError):
    pass


class NovelExportService:
    def __init__(
        self, database: Database, renderer: Callable[..., bytes] = render_novel_docx
    ) -> None:
        self.database = database
        self.renderer = renderer

    async def options(self, *, tenant_id: str, project_id: str) -> dict[str, object]:
        async with self.database.session() as session:
            project = await _project(session, tenant_id, project_id)
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project.id)
                )
            ).one()
            adopted = set(
                await session.scalars(
                    select(NovelDocumentRevisionModel.chapter_id).where(
                        NovelDocumentRevisionModel.project_id == project.id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            )
            volumes = []
            for volume in story_map.volumes:
                chapters = [
                    {
                        "id": str(chapter["id"]),
                        "title": str(chapter["title"]),
                        "status": "done" if str(chapter["id"]) in adopted else "empty",
                        "selectable": str(chapter["id"]) in adopted,
                    }
                    for chapter in volume.get("chapters", [])
                ]
                selected = sum(bool(item["selectable"]) for item in chapters)
                volumes.append(
                    {
                        "id": str(volume["id"]),
                        "title": str(volume["title"]),
                        "selection": "all"
                        if chapters and selected == len(chapters)
                        else "partial"
                        if selected
                        else "none",
                        "chapters": chapters,
                    }
                )
            return {"project_id": project.id, "volumes": volumes}

    async def export(
        self,
        *,
        tenant_id: str,
        project_id: str,
        chapter_ids: tuple[str, ...],
        form: str,
        idempotency_key: str,
    ) -> NovelExportManifestModel:
        if not chapter_ids or len(chapter_ids) != len(set(chapter_ids)):
            raise NovelDeliveryError("export scope must contain unique chapters")
        if form not in {"clean", "working"}:
            raise NovelDeliveryError("unsupported Novel export form")
        async with self.database.session() as session:
            project = await _project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(NovelExportManifestModel).where(
                        NovelExportManifestModel.project_id == project_id,
                        NovelExportManifestModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing and existing.status == DeliveryStatus.SUCCEEDED:
                return existing
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project_id)
                )
            ).one()
            revisions = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.chapter_id.in_(chapter_ids),
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            )
            by_chapter = {item.chapter_id: item for item in revisions}
            if set(chapter_ids) != set(by_chapter):
                raise NovelDeliveryError("only completed chapters can be exported")
            chapters = _ordered_chapters(story_map.volumes, chapter_ids, by_chapter)
            manifest = existing or NovelExportManifestModel(
                project_id=project_id,
                idempotency_key=idempotency_key,
                scope=list(chapter_ids),
                form=form,
                status=DeliveryStatus.PENDING,
            )
            if existing is None:
                session.add(manifest)
            manifest.attempts = (manifest.attempts or 0) + 1
            manifest.error = None
            try:
                artifact = self.renderer(project_name=project.name, chapters=tuple(chapters))
            except Exception as error:
                manifest.status = DeliveryStatus.FAILED
                manifest.error = str(error)[:500]
                await session.flush()
                return manifest
            manifest.artifact = artifact
            manifest.artifact_sha256 = hashlib.sha256(artifact).hexdigest()
            manifest.byte_size = len(artifact)
            manifest.status = DeliveryStatus.SUCCEEDED
            await _event(session, tenant_id, project_id, manifest)
            await session.flush()
            return manifest


async def _project(session, tenant_id: str, project_id: str) -> ProjectModel:
    project = await session.get(ProjectModel, project_id)
    if project is None or project.tenant_id != tenant_id or project.medium != "novel":
        raise NovelDeliveryError("Novel project is outside tenant scope")
    return project


def _ordered_chapters(volumes, scope, by_chapter) -> list[NovelExportChapter]:
    selected = set(scope)
    result = []
    for volume in volumes:
        for chapter in volume.get("chapters", []):
            chapter_id = str(chapter["id"])
            if chapter_id in selected:
                revision = by_chapter[chapter_id]
                result.append(
                    NovelExportChapter(
                        volume_title=str(volume["title"]),
                        chapter_title=str(chapter["title"]),
                        blocks=tuple(NovelBlock.model_validate(item) for item in revision.blocks),
                    )
                )
    if len(result) != len(selected):
        raise NovelDeliveryError("export scope contains a chapter outside StoryMap")
    return result


async def _event(session, tenant_id: str, project_id: str, manifest) -> None:
    stream_key = f"project:{project_id}"
    sequence = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(ProjectEventModel.sequence), 0)).where(
                    ProjectEventModel.stream_key == stream_key
                )
            )
            or 0
        )
        + 1
    )
    session.add(
        ProjectEventModel(
            tenant_id=tenant_id,
            project_id=project_id,
            stream_key=stream_key,
            sequence=sequence,
            event_key=f"novel:export:{manifest.id}",
            event_type="node",
            actor={"type": "user", "id": tenant_id},
            aggregate={"type": "novel_export", "id": manifest.id},
            correlation_id=manifest.id,
            idempotency_key=manifest.idempotency_key,
            payload={"action": "novel.exported", "scope": manifest.scope, "form": manifest.form},
        )
    )
