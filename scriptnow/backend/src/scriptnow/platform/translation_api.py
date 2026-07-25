"""Translation project API — faithful literary translation with side-by-side tracking.

A translation project references a source novel project and tracks per-chapter
translation status. Uses the existing FaithfulTranslationService for actual translation.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectMedium, ProjectModel
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.translation import FaithfulTranslationService


class CreateTranslationRequest(BaseModel):
    source_project_id: str = Field(min_length=36, max_length=36)
    target_language: str = Field(min_length=1, max_length=80)
    translation_mode: str = Field(default="faithful")


class TranslationChapter(BaseModel):
    chapter_id: str
    title: str
    source_text: str  # original text blocks
    translated_text: str | None = None  # translated text blocks
    status: str = "pending"  # pending, translating, completed, failed


async def _tenant_id(database: Database, access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(401, "authentication required")
    async with database.session() as session:
        from scriptnow.platform.models import RefreshTokenModel
        from datetime import datetime, timezone
        token = await session.get(RefreshTokenModel, access_token)
        if token is None or (token.expires_at and token.expires_at < datetime.now(timezone.utc)):
            raise HTTPException(401, "session expired")
        return token.tenant_id


def create_translation_router(database: Database, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/translation")
    run_coordinator = RunCoordinator(database)
    translator = FaithfulTranslationService(database, settings)

    @router.post("/projects")
    async def create_translation_project(
        body: CreateTranslationRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        actor = await auth_context(access_token)
        tid = str(actor.tenant_id)

        async with database.session() as session:
            source = await session.get(ProjectModel, body.source_project_id)
            if source is None or source.tenant_id != tid:
                raise HTTPException(404, "source project not found")
            if source.medium != "novel":
                raise HTTPException(400, "translation source must be a novel project")

            project = ProjectModel(
                tenant_id=tid,
                name=f"{source.name} · {body.target_language}",
                medium=ProjectMedium.TRANSLATION,
                source_mode="original",
                direction={
                    "source_project_id": body.source_project_id,
                    "source_language": source.direction.get("language", "en-US"),
                    "target_language": body.target_language,
                    "translation_mode": body.translation_mode,
                },
            )
            session.add(project)
            await session.flush()
            pid = project.id

        return {"id": pid, "name": project.name, "medium": "translation"}

    @router.get("/projects/{project_id}/chapters")
    async def list_chapters(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        actor = await auth_context(access_token)
        tid = str(actor.tenant_id)

        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "project not found")
            if project.medium != "translation":
                raise HTTPException(400, "not a translation project")

            direction = project.direction or {}
            source_id = direction.get("source_project_id")
            if not source_id:
                return []

            source = await session.get(ProjectModel, source_id)
            if source is None:
                raise HTTPException(404, "source project not found")

            from scriptnow.novel.project import NovelStoryMapModel
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(
                        NovelStoryMapModel.project_id == source_id
                    )
                )
            ).one_or_none()

            if story_map is None:
                return []

            chapters = []
            for vol in story_map.volumes:
                for ch in vol.get("chapters", []):
                    cid = str(ch.get("id"))
                    # Check if translation exists
                    revisions = list(
                        await session.scalars(
                            select(NovelDocumentRevisionModel).where(
                                NovelDocumentRevisionModel.project_id == project_id,
                                NovelDocumentRevisionModel.chapter_id == cid,
                                NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                            )
                        )
                    )
                    translated_text = None
                    status = "pending"
                    if revisions:
                        latest = revisions[-1]
                        blocks = latest.blocks
                        translated_text = " ".join(
                            str(b.get("text", "")) for b in blocks
                            if isinstance(b, dict) and b.get("type") in ("prose", "dialogue")
                        )
                        status = "completed"

                    chapters.append({
                        "chapter_id": cid,
                        "title": str(ch.get("title", "")),
                        "source_text": "",  # loaded on demand
                        "translated_text": translated_text,
                        "status": status,
                    })

        return chapters

    @router.post("/projects/{project_id}/chapters/{chapter_id}/translate")
    async def translate_chapter(
        project_id: str,
        chapter_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        actor = await auth_context(access_token)
        tid = str(actor.tenant_id)
        import uuid

        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "project not found")

            direction = project.direction or {}
            source_id = direction.get("source_project_id")
            target_lang = direction.get("target_language", "")
            source_lang = direction.get("source_language", "en-US")

            source = await session.get(ProjectModel, source_id)
            if source is None:
                raise HTTPException(404, "source project not found")

            from scriptnow.novel.project import NovelStoryMapModel
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == source_id)
                )
            ).one_or_none()

            if story_map is None:
                raise HTTPException(400, "source story map not found")

            # Find the chapter in source
            chapter = None
            for vol in story_map.volumes:
                for ch in vol.get("chapters", []):
                    if str(ch.get("id")) == chapter_id:
                        chapter = ch
                        break

            if chapter is None:
                raise HTTPException(404, "chapter not found in source")

            source_revisions = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == source_id,
                        NovelDocumentRevisionModel.chapter_id == chapter_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            )

            if not source_revisions:
                raise HTTPException(400, "source chapter not yet written")

        # Build TranslationUnit from source
        from scriptnow.platform.translation_contracts import TranslationUnit
        source_rev = source_revisions[-1]
        source_blocks = [dict(b) if isinstance(b, dict) else {"type": "prose", "text": str(b)} for b in list(source_rev.blocks)]

        unit = TranslationUnit(
            titles={source_lang: str(chapter.get("title", ""))},
            blocks=tuple(source_blocks),
        )

        # Translate
        idem_key = f"trans:{project_id}:{chapter_id}:{uuid.uuid4().hex[:12]}"
        translated = await translator.translate(
            tenant_id=tid,
            project_id=project_id,
            source_language=source_lang,
            target_language=target_lang,
            units=(unit,),
            idempotency_key=idem_key,
        )

        # Store translation in the translation project
        from scriptnow.novel.domain import NovelDocumentRevisionModel as Rev
        async with database.session() as session:
            rev = Rev(
                project_id=project_id,
                chapter_id=chapter_id,
                blocks=list(translated[0].blocks),
                status=NovelRevisionStatus.ADOPTED,
                source="translation",
                revision_number=1,
            )
            session.add(rev)
            await session.flush()

        return {
            "chapter_id": chapter_id,
            "status": "completed",
            "blocks": list(translated[0].blocks),
        }

    return router
