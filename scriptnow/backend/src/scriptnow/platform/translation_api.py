"""Translation project API — faithful literary translation."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.platform.auth import AuthService
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectMedium, ProjectModel
from scriptnow.platform.translation import FaithfulTranslationService
from scriptnow.platform.translation_glossary import (
    create_glossary,
    get_glossary,
)


class CreateTranslationRequest(BaseModel):
    source_project_id: str = Field(min_length=36, max_length=36)
    target_language: str = Field(min_length=1, max_length=80)
    translation_mode: str = Field(default="faithful")


def create_translation_router(
    database: Database, auth: AuthService, settings: Settings
) -> APIRouter:
    router = APIRouter(prefix="/translation")
    translator = FaithfulTranslationService(database, settings)

    @router.post("/projects")
    async def create_translation_project(
        body: CreateTranslationRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
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
        create_glossary(
            project_id=pid,
            source_language=source.direction.get("language", "en-US"),
            target_language=body.target_language,
        )
        return {"id": pid, "name": project.name, "medium": "translation"}

    @router.get("/projects/{project_id}/chapters")
    async def list_chapters(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "project not found")
            direction = project.direction or {}
            source_id = direction.get("source_project_id")
            if not source_id:
                return []
            from scriptnow.novel.project import NovelStoryMapModel
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == source_id)
                )
            ).one_or_none()
            if story_map is None:
                return []
            chapters = []
            for vol in story_map.volumes:
                for ch in vol.get("chapters", []):
                    cid = str(ch.get("id"))
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
                        blocks = revisions[-1].blocks
                        translated_text = " ".join(
                            str(b.get("text", "")) for b in blocks
                            if isinstance(b, dict) and b.get("type") in ("prose", "dialogue")
                        )
                        status = "completed"
                    chapters.append({
                        "chapter_id": cid,
                        "title": str(ch.get("title", "")),
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
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
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
            chapter = None
            for vol in story_map.volumes:
                for ch in vol.get("chapters", []):
                    if str(ch.get("id")) == chapter_id:
                        chapter = ch
                        break
            if chapter is None:
                raise HTTPException(404, "chapter not found")
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
        from scriptnow.platform.translation_contracts import TranslationUnit
        source_rev = source_revisions[-1]
        source_blocks = [
            dict(b) if isinstance(b, dict) else {"type": "prose", "text": str(b)}
            for b in list(source_rev.blocks)
        ]
        unit = TranslationUnit(
            titles={source_lang: str(chapter.get("title", ""))},
            blocks=tuple(source_blocks),
        )
        idem_key = f"trans:{project_id}:{chapter_id}:{uuid.uuid4().hex[:12]}"
        glossary = get_glossary(project_id)
        glossary_block = glossary.to_prompt_block() if glossary else ""
        translated = await translator.translate(
            tenant_id=tid,
            project_id=project_id,
            source_language=source_lang,
            target_language=target_lang,
            units=(unit,),
            idempotency_key=idem_key,
            glossary_block=glossary_block,
        )
        async with database.session() as session:
            rev = NovelDocumentRevisionModel(
                project_id=project_id,
                chapter_id=chapter_id,
                blocks=list(translated[0].blocks),
                status=NovelRevisionStatus.ADOPTED,
                source="translation",
                revision_number=1,
                idempotency_key=idem_key,
            )
            session.add(rev)
            await session.flush()
        # Update glossary with extracted terms from translated pair
        glossary = get_glossary(project_id)
        if glossary:
            source_text = " ".join(
                str(b.get("text", "")) for b in source_blocks
                if isinstance(b, dict) and b.get("type") in ("prose", "dialogue")
            )
            translated_text = " ".join(
                str(b.get("text", "")) for b in translated[0].blocks
                if isinstance(b, dict) and b.get("type") in ("prose", "dialogue")
            )
            glossary.extract_from_text_pair(source_text, translated_text)
        return {
            "chapter_id": chapter_id,
            "status": "completed",
            "blocks": list(translated[0].blocks),
        }

    @router.post("/projects/{project_id}/translate-all")
    async def translate_all(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        """Translate all pending chapters in sequence, accumulating glossary."""
        context = await auth.validate_access(access_token)
        str(context.tenant_id)

        # Get all pending chapters
        chapters_raw = await list_chapters(project_id=project_id, access_token=access_token)
        pending = [c for c in chapters_raw if c["status"] == "pending"]
        if not pending:
            return {"status": "no_pending", "message": "all chapters already translated"}

        results = []
        glossary = get_glossary(project_id)
        for ch in pending:
            cid = ch["chapter_id"]
            try:
                await translate_chapter(
                    project_id=project_id,
                    chapter_id=cid,
                    access_token=access_token,
                )
                results.append({"chapter_id": cid, "status": "completed"})
            except Exception as exc:
                results.append({"chapter_id": cid, "status": "failed", "error": str(exc)})

        glossary_info = glossary.to_dict() if glossary else {}
        return {
            "status": "completed",
            "translated": len([r for r in results if r["status"] == "completed"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "chapters": results,
            "glossary_terms": glossary_info.get("term_count", 0),
        }

    @router.get("/projects/{project_id}/glossary")
    async def get_glossary_endpoint(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "project not found")
        glossary = get_glossary(project_id)
        if glossary is None:
            return {"terms": {}}
        return glossary.to_dict()

    @router.put("/projects/{project_id}/glossary")
    async def update_glossary_endpoint(
        project_id: str,
        body: dict,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        str(context.tenant_id)
        glossary = get_glossary(project_id)
        if glossary is None:
            raise HTTPException(404, "glossary not found")
        if "terms" in body:
            glossary.add_batch(body["terms"])
        return glossary.to_dict()

    @router.post("/documents")
    async def upload_and_translate(
        file: UploadFile,
        target_language: str = Form(...),
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        """Upload a document (TXT/PDF/DOCX), extract text, create translation project."""
        import os
        import uuid

        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)

        # Read file content
        raw = await file.read()
        ext = os.path.splitext(file.filename or "")[1].lower()

        # Extract text
        text = ""
        if ext == ".txt":
            text = raw.decode("utf-8", errors="replace")
        elif ext == ".pdf":
            import subprocess
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    ["pdftotext", "-layout", tmp_path, "-"],
                    capture_output=True, text=True, timeout=30
                )
                text = result.stdout or raw.decode("utf-8", errors="replace")
            except Exception:
                text = f"[PDF: {file.filename} - binary content, {len(raw)} bytes]"
            finally:
                os.unlink(tmp_path)
        elif ext == ".docx":
            try:
                import io

                from docx import Document
                doc = Document(io.BytesIO(raw))
                text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except Exception:
                text = raw.decode("utf-8", errors="replace")
        else:
            raise HTTPException(400, f"unsupported file type: {ext}")

        if not text.strip():
            raise HTTPException(400, "document contains no extractable text")

        # Split into chapters by double newlines (approximate)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        # Group into chunks of ~2000 chars for chapter-like units
        chapters_text = []
        current = []
        current_len = 0
        for p in paragraphs:
            if current_len > 2000 and current:
                chapters_text.append("\n\n".join(current))
                current = []
                current_len = 0
            current.append(p)
            current_len += len(p)
        if current:
            chapters_text.append("\n\n".join(current))
        if not chapters_text:
            chapters_text = [text]

        # Create translation project
        project_name = os.path.splitext(file.filename or "translation")[0]
        async with database.session() as session:
            project = ProjectModel(
                tenant_id=tid,
                name=f"{project_name} · {target_language}",
                medium=ProjectMedium.TRANSLATION,
                source_mode="original",
                direction={
                    "source_language": "auto",
                    "target_language": target_language,
                    "translation_mode": "faithful",
                    "source_type": "upload",
                    "original_filename": file.filename,
                },
            )
            session.add(project)
            await session.flush()
            pid = project.id

        create_glossary(
            project_id=pid,
            source_language="auto",
            target_language=target_language,
        )

        # Translate each chunk
        from scriptnow.platform.translation_contracts import TranslationUnit
        results = []
        for idx, chunk_text in enumerate(chapters_text):
            chapter_id = f"upload-ch-{idx + 1}"
            unit = TranslationUnit(
                titles={"upload": f"Section {idx + 1}"},
                blocks=({"type": "prose", "text": chunk_text},),
            )
            idem_key = f"trans:{pid}:{chapter_id}:{uuid.uuid4().hex[:12]}"
            try:
                glossary = get_glossary(pid)
                glossary_block = glossary.to_prompt_block() if glossary else ""
                translated = await translator.translate(
                    tenant_id=tid,
                    project_id=pid,
                    source_language="auto",
                    target_language=target_language,
                    units=(unit,),
                    idempotency_key=idem_key,
                    glossary_block=glossary_block,
                )
                async with database.session() as session:
                    rev = NovelDocumentRevisionModel(
                        project_id=pid,
                        chapter_id=chapter_id,
                        blocks=list(translated[0].blocks),
                        status=NovelRevisionStatus.ADOPTED,
                        source="translation",
                        revision_number=1,
                        idempotency_key=idem_key,
                    )
                    session.add(rev)
                    await session.flush()
                results.append({"chapter": idx + 1, "status": "completed"})
            except Exception as exc:
                results.append({"chapter": idx + 1, "status": "failed", "error": str(exc)})

        return {
            "project_id": pid,
            "name": project.name,
            "chapters": len(results),
            "completed": len([r for r in results if r["status"] == "completed"]),
            "results": results,
        }

    return router
