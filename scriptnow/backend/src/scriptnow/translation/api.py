"""Translation application API — coordinates platform and novel adapters."""

import asyncio
import hashlib
import json
import mimetypes
from contextlib import suppress
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Cookie, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.domain import (
    NovelBlueprintCandidateModel,
    NovelDocumentRevisionModel,
    NovelRevisionStatus,
)
from scriptnow.novel.export import NovelExportChapter, render_novel_docx
from scriptnow.platform.active_runs import ActiveRunRegistry
from scriptnow.platform.auth import AuthService
from scriptnow.platform.auth_api import ACCESS_COOKIE
from scriptnow.platform.config import Settings
from scriptnow.platform.context_retrieval import ContextRequest, RetrievalMode
from scriptnow.platform.creative_delivery import CreativeDeliveryService
from scriptnow.platform.creative_operations import (
    CreativeOperationStore,
    coherent_run_status,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeStageStatus,
    ProjectMedium,
    ProjectModel,
    ProjectSnapshotModel,
    RunStatus,
)
from scriptnow.platform.retrieval_runtime import (
    estimate_tokens,
    retrieval_policy,
    retrieval_service,
)
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType
from scriptnow.platform.source_text import extract_source_text
from scriptnow.platform.translation import FaithfulTranslationService
from scriptnow.platform.translation_contracts import TranslationError
from scriptnow.platform.translation_glossary import (
    create_glossary,
    get_glossary,
)
from scriptnow.translation.context import FaithfulTranslationContextAdapter
from scriptnow.translation.domain import (
    TranslationCorrectionModel,
    TranslationGlossaryTermModel,
    TranslationSnapshotContentModel,
)


class CreateTranslationRequest(BaseModel):
    source_project_id: str = Field(min_length=36, max_length=36)
    target_language: str = Field(min_length=1, max_length=80)
    translation_mode: str = Field(default="faithful")


class CreateTranslationVersionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class GlossaryTermRequest(BaseModel):
    source_term: str = Field(min_length=1, max_length=240)
    target_term: str = Field(default="", max_length=240)
    status: str = Field(default="confirmed", pattern="^(candidate|confirmed)$")


class ApplyGlossaryCorrectionsRequest(BaseModel):
    term_id: str | None = None


def _translation_documents(records: list[NovelDocumentRevisionModel]) -> list[dict[str, object]]:
    return [
        {
            "chapter_id": item.chapter_id,
            "revision_id": item.id,
            "blocks": item.blocks,
        }
        for item in sorted(records, key=lambda value: value.chapter_id)
    ]


def _translation_hash(documents: list[dict[str, object]]) -> str:
    normalized = [
        {"chapter_id": item["chapter_id"], "blocks": item["blocks"]}
        for item in documents
    ]
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


async def _persistent_glossary(
    database: Database, project: ProjectModel
):
    direction = project.direction or {}
    glossary = create_glossary(
        project.id,
        str(direction.get("source_language") or "auto"),
        str(direction.get("target_language") or ""),
    )
    async with database.session() as session:
        records = list(
            await session.scalars(
                select(TranslationGlossaryTermModel).where(
                    TranslationGlossaryTermModel.project_id == project.id,
                    TranslationGlossaryTermModel.status == "confirmed",
                    TranslationGlossaryTermModel.target_term != "",
                )
            )
        )
    for item in records:
        glossary.add(item.source_term, item.target_term, confirmed=True)
    return glossary


async def _add_chapter_glossary_candidates(
    database: Database,
    *,
    translation_project_id: str,
    source_project_id: str,
    chapter: dict[str, object],
) -> int:
    """Add blueprint terms actually referenced by a translated chapter."""
    anchor_ids = {
        str(anchor_id)
        for beat in chapter.get("beats", [])
        if isinstance(beat, dict)
        for anchor_id in beat.get("anchor_ids", [])
    }
    if not anchor_ids:
        return 0
    async with database.session() as session:
        blueprint = (
            await session.scalars(
                select(NovelBlueprintCandidateModel).where(
                    NovelBlueprintCandidateModel.project_id == source_project_id,
                    NovelBlueprintCandidateModel.status == "adopted",
                )
            )
        ).one_or_none()
        if blueprint is None:
            return 0
        existing = set(
            await session.scalars(
                select(TranslationGlossaryTermModel.source_term).where(
                    TranslationGlossaryTermModel.project_id
                    == translation_project_id
                )
            )
        )
        added = 0
        for anchor in blueprint.draft.get("anchors", []):
            if not isinstance(anchor, dict) or str(anchor.get("id")) not in anchor_ids:
                continue
            name = str(anchor.get("name") or "").strip()
            kind = str(anchor.get("kind") or "")
            if (
                kind not in {"character", "location", "motif", "world"}
                or not name
                or len(name) > 80
                or name in existing
            ):
                continue
            session.add(
                TranslationGlossaryTermModel(
                    id=uuid4().hex,
                    project_id=translation_project_id,
                    source_term=name,
                    target_term="",
                    status="candidate",
                    source="automatic",
                )
            )
            existing.add(name)
            added += 1
        return added


def _validate_upload_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(400, "invalid file name")
    name = filename.strip()
    if any(char in name for char in ("/", "\\", "..")):
        raise HTTPException(400, "invalid file name")
    return name


def _detect_extension(filename: str | None, content_type: str | None) -> str:
    path_ext = filename.rsplit(".", 1)[-1] if filename and "." in filename else ""
    candidate = f".{path_ext.lower()}" if path_ext else ""
    if candidate in {".txt", ".pdf", ".docx"}:
        return candidate
    if content_type:
        guessed = mimetypes.guess_extension(content_type.lower().split(";")[0].strip())
        if guessed in {".txt", ".pdf", ".docx"}:
            return guessed
    raise HTTPException(400, "unsupported file type")


def _extract_uploaded_text(content: bytes, ext: str, filename: str) -> str:
    media_type = {
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }[ext]

    try:
        text = extract_source_text(content, media_type).strip()
    except Exception as error:
        raise HTTPException(
            400,
            f"failed to parse {ext[1:].upper()} file: {filename}",
        ) from error

    if not text.strip():
        raise HTTPException(400, f"document contains no extractable text: {filename}")
    return text


def create_translation_router(
    database: Database,
    auth: AuthService,
    settings: Settings,
    active_runs: ActiveRunRegistry,
) -> APIRouter:
    router = APIRouter(prefix="/translation")
    translator = FaithfulTranslationService(database, settings)
    deliveries = CreativeDeliveryService(database)
    operations = CreativeOperationStore(database)
    run_events = PersistentRunEventLog(database)

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
                    source_revisions = list(
                        await session.scalars(
                            select(NovelDocumentRevisionModel).where(
                                NovelDocumentRevisionModel.project_id == source_id,
                                NovelDocumentRevisionModel.chapter_id == cid,
                                NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                            )
                        )
                    )
                    source_text = None
                    if source_revisions:
                        source_text = "\n\n".join(
                            str(block.get("text", ""))
                            for block in source_revisions[-1].blocks
                            if isinstance(block, dict)
                            and block.get("type") in ("prose", "dialogue")
                            and block.get("text")
                        )
                    translated_text = None
                    translated_title = None
                    status = "pending"
                    if revisions:
                        blocks = revisions[-1].blocks
                        translated_title = next(
                            (
                                str(block.get("text", ""))
                                for block in blocks
                                if isinstance(block, dict)
                                and block.get("type") == "heading"
                                and block.get("text")
                            ),
                            None,
                        )
                        translated_text = " ".join(
                            str(b.get("text", "")) for b in blocks
                            if isinstance(b, dict) and b.get("type") in ("prose", "dialogue")
                        )
                        status = "completed"
                    chapters.append({
                        "chapter_id": cid,
                        "title": str(ch.get("title", "")),
                        "source_text": source_text,
                        "translated_title": translated_title,
                        "translated_text": translated_text,
                        "status": status,
                    })
        return chapters

    async def _translate_chapter_work(
        project_id: str,
        chapter_id: str,
        tenant_id: str,
        *,
        run_id: str | None = None,
    ):
        tid = tenant_id
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
        glossary = await _persistent_glossary(database, project)
        glossary_block = glossary.to_prompt_block() if glossary else ""
        context_request = ContextRequest(
            tenant_id=tid,
            project_id=project_id,
            retrieval_project_ids=(str(source_id),),
            domain="translation",
            stage="chapter_translation",
            operation="faithful_translate",
            unit_ref=chapter_id,
            user_intent=f"{source_lang} to {target_lang}",
            required_dimensions=(
                "source_fidelity",
                "terminology",
                "voice",
                "continuity",
            ),
            risk_level="high",
            policy_ref="settings:faithful_translation_context",
        )
        persisted_context = await retrieval_service(database, settings).build(
            request=context_request,
            policy=retrieval_policy(
                settings,
                allowed_sources=(
                    "source_revision",
                    "translation_glossary",
                    "prior_translation",
                    "workspace_source",
                    "narrative_graph_source",
                ),
                coverage_requirements={
                    "source_fidelity": 1.0,
                    "voice": 1.0,
                    "continuity": 1.0,
                },
                modes=(RetrievalMode.LEXICAL, RetrievalMode.NARRATIVE_GRAPH),
            ),
            adapter=FaithfulTranslationContextAdapter(
                database,
                token_counter=estimate_tokens,
            ),
        )
        try:
            translated = await translator.translate(
                tenant_id=tid,
                project_id=project_id,
                source_language=source_lang,
                target_language=target_lang,
                units=(unit,),
                idempotency_key=idem_key,
                glossary_block=glossary_block,
                context_pack=persisted_context.context_pack.model_dump(mode="json"),
                retrieval_manifest_id=persisted_context.manifest_id,
                run_id=run_id,
            )
        except TranslationError as error:
            raise HTTPException(
                422,
                "本次译文未通过完整性校验，未写入任何内容。请重新翻译本章。",
            ) from error
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
        await _add_chapter_glossary_candidates(
            database,
            translation_project_id=project_id,
            source_project_id=str(source_id),
            chapter=chapter,
        )
        # Update glossary with extracted terms from translated pair
        glossary = await _persistent_glossary(database, project)
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
            async with database.session() as session:
                existing_terms = set(
                    await session.scalars(
                        select(TranslationGlossaryTermModel.source_term).where(
                            TranslationGlossaryTermModel.project_id == project_id
                        )
                    )
                )
                for source_term, target_term in glossary.terms.items():
                    if source_term not in existing_terms:
                        session.add(
                            TranslationGlossaryTermModel(
                                id=uuid4().hex,
                                project_id=project_id,
                                source_term=source_term,
                                target_term=target_term,
                                status="candidate" if not target_term else "confirmed",
                                source="automatic",
                            )
                        )
        return {
            "chapter_id": chapter_id,
            "status": "completed",
            "blocks": list(translated[0].blocks),
            "revision_id": rev.id,
            "revision_number": rev.revision_number,
        }

    async def _background_translate_chapter(
        *,
        tenant_id: str,
        project_id: str,
        chapter_id: str,
        run_id: str,
        operation_id: str,
        stage_run_id: str,
        input_digest: str,
    ) -> None:
        coordinator = RunCoordinator(database)
        try:
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.RUNNING,
            )
            result = await _translate_chapter_work(
                project_id,
                chapter_id,
                tenant_id,
                run_id=run_id,
            )
            revision_id = str(result["revision_id"])
            revision_number = int(result["revision_number"])
            artifact_ref_id = await operations.register_artifact(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                domain="translation",
                artifact_type="translation_revision",
                artifact_id=revision_id,
                revision=revision_number,
                status="adopted",
                schema_version=1,
                input_digest=input_digest,
                dependency_versions={"chapter_id": chapter_id},
                provenance={"source": "agent", "run_id": run_id},
            )
            await operations.save_checkpoint(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                checkpoint_key=f"translation.chapter.translate:{revision_id}",
                state_format="json",
                state_payload=json.dumps(
                    {
                        "chapter_id": chapter_id,
                        "revision_id": revision_id,
                        "revision_number": revision_number,
                        "artifact_ref_id": artifact_ref_id,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode(),
                resume_metadata={"next_action": "review_translation"},
                is_complete=True,
            )
            await operations.finish_stage(
                tenant_id=tenant_id,
                operation_id=operation_id,
                stage_run_id=stage_run_id,
                status=CreativeStageStatus.READY,
            )
            await run_events.append(
                tenant_id=tenant_id,
                run_id=run_id,
                event_key="translation-persisted",
                type=RunEventType.TERMINAL,
                payload={
                    "block": "system",
                    "phase": "end",
                    "title": "本章译文已保存",
                    "chapter_id": chapter_id,
                    "revision_id": revision_id,
                    "runtime": "agentscope",
                },
                correlation_id=run_id,
            )
            await coordinator.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.SUCCEEDED,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await coordinator.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.CANCELLED,
                )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.CANCELLED,
                )
            raise
        except Exception as error:
            with suppress(Exception):
                current = await coordinator.status(
                    tenant_id=tenant_id, run_id=run_id
                )
                if current is not None and current.status in {
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                    RunStatus.WAITING,
                }:
                    await coordinator.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code="translation_chapter_failed",
                    )
            with suppress(Exception):
                await operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation_id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.FAILED,
                    error={"code": "translation_chapter_failed", "message": str(error)},
                )

    @router.post("/projects/{project_id}/chapters/{chapter_id}/translate")
    async def translate_chapter(
        project_id: str,
        chapter_id: str,
        background: Annotated[bool, Query()] = False,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tenant_id = str(context.tenant_id)
        if not background:
            return await _translate_chapter_work(project_id, chapter_id, tenant_id)

        idempotency_key = f"translation:{project_id}:{chapter_id}:{uuid4().hex}"
        coordinator = RunCoordinator(database)
        run = await coordinator.enqueue(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
        creative_session_id = await operations.get_or_open_session(
            tenant_id=tenant_id,
            project_id=project_id,
            active_domain="translation",
        )
        turn_id = await operations.append_turn(
            tenant_id=tenant_id,
            session_id=creative_session_id,
            actor={"type": "user"},
            input={"command": "translation.chapter.translate", "chapter_id": chapter_id},
        )
        input_digest = hashlib.sha256(
            json.dumps(
                {"project_id": project_id, "chapter_id": chapter_id},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        operation = await operations.enqueue_operation(
            tenant_id=tenant_id,
            session_id=creative_session_id,
            turn_id=turn_id,
            run_id=run.id,
            command="translation.chapter.translate",
            domain="translation",
            stage="translate",
            idempotency_key=idempotency_key,
            policy_snapshot={"delivery": "background", "adoption": "automatic"},
        )
        stage_run_id = await operations.start_stage(
            tenant_id=tenant_id,
            operation_id=operation.id,
            stage_key="translate",
            attempt=1,
            input_digest=input_digest,
        )
        task = asyncio.create_task(
            _background_translate_chapter(
                tenant_id=tenant_id,
                project_id=project_id,
                chapter_id=chapter_id,
                run_id=run.id,
                operation_id=operation.id,
                stage_run_id=stage_run_id,
                input_digest=input_digest,
            )
        )
        active_runs.track(run.id, task)
        return {
            "chapter_id": chapter_id,
            "status": run.status,
            "run_id": run.id,
            "operation_id": operation.id,
            "creative_session_id": creative_session_id,
        }

    @router.get("/projects/{project_id}/runs/{run_id}")
    async def translation_run(
        project_id: str,
        run_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        run = await RunCoordinator(database).status(
            tenant_id=str(context.tenant_id),
            run_id=run_id,
        )
        if run is None or run.project_id != project_id:
            raise HTTPException(404, "translation run not found")
        operation = await operations.operation_for_run(
            tenant_id=str(context.tenant_id),
            run_id=run_id,
        )
        return {
            "run_id": run.id,
            "status": coherent_run_status(
                run.status, operation.status if operation else None
            ),
            "state_version": run.state_version,
            "waiting_reason": run.waiting_reason,
            "error_code": run.error_code,
            "operation_id": operation.id if operation else None,
            "creative_session_id": operation.session_id if operation else None,
            "operation_status": operation.status if operation else None,
            "stage": operation.stage if operation else None,
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
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
        glossary = await _persistent_glossary(database, project) if project else None
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

    @router.post("/projects/{project_id}/imports")
    async def import_translation_chapter(
        project_id: str,
        chapter_id: Annotated[str, Form()],
        file: UploadFile,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        """Import an existing human translation as a new adopted revision."""
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        raw = await file.read()
        if not raw or len(raw) > settings.upload_max_file_bytes:
            raise HTTPException(413, "译文文件为空或超过项目允许的单文件大小")
        filename = file.filename or "translation.txt"
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension == "txt":
            text = raw.decode("utf-8", errors="replace")
        elif extension == "docx":
            import io

            from docx import Document

            try:
                document = Document(io.BytesIO(raw))
                text = "\n\n".join(
                    paragraph.text.strip()
                    for paragraph in document.paragraphs
                    if paragraph.text.strip()
                )
            except Exception as error:
                raise HTTPException(422, "无法读取该 DOCX 译文文件") from error
        else:
            raise HTTPException(415, "目前支持导入 UTF-8 TXT 或 DOCX 译文")
        paragraphs = [value.strip() for value in text.splitlines() if value.strip()]
        if not paragraphs:
            raise HTTPException(422, "译文文件中没有可导入的正文")

        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != tid
                or project.medium != ProjectMedium.TRANSLATION
            ):
                raise HTTPException(404, "翻译项目不存在")
            source_id = str((project.direction or {}).get("source_project_id") or "")
            from scriptnow.novel.project import NovelStoryMapModel

            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(
                        NovelStoryMapModel.project_id == source_id
                    )
                )
            ).one_or_none()
            valid_chapter_ids = {
                str(chapter.get("id"))
                for volume in (story_map.volumes if story_map else [])
                for chapter in volume.get("chapters", [])
            }
            if chapter_id not in valid_chapter_ids:
                raise HTTPException(404, "目标章节不在源作品 StoryMap 中")
            current = (
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.chapter_id == chapter_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            revision_number = int(
                await session.scalar(
                    select(
                        func.coalesce(
                            func.max(NovelDocumentRevisionModel.revision_number), 0
                        )
                    ).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.chapter_id == chapter_id,
                    )
                )
                or 0
            ) + 1
            if current:
                current.status = NovelRevisionStatus.SUPERSEDED
            revision = NovelDocumentRevisionModel(
                project_id=project_id,
                chapter_id=chapter_id,
                revision_number=revision_number,
                base_revision_id=current.id if current else None,
                source="human_import",
                blocks=[
                    {
                        "block_id": f"import-{revision_number}-{index + 1}",
                        "type": "prose",
                        "text": paragraph,
                    }
                    for index, paragraph in enumerate(paragraphs)
                ],
                status=NovelRevisionStatus.ADOPTED,
                idempotency_key=f"translation:import:{uuid4().hex}",
            )
            session.add(revision)
            await session.flush()
            return {
                "chapter_id": chapter_id,
                "revision_id": revision.id,
                "revision_number": revision_number,
                "paragraph_count": len(paragraphs),
            }

    @router.get("/projects/{project_id}/export.docx")
    async def export_translation(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        """Export adopted translations in the source StoryMap order."""
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != tid
                or project.medium != ProjectMedium.TRANSLATION
            ):
                raise HTTPException(404, "翻译项目不存在")
            source_id = str((project.direction or {}).get("source_project_id") or "")
            from scriptnow.novel.project import NovelStoryMapModel

            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(
                        NovelStoryMapModel.project_id == source_id
                    )
                )
            ).one_or_none()
            if story_map is None:
                raise HTTPException(409, "源作品尚未形成可导出的章节结构")
            revisions = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            )
            by_chapter = {item.chapter_id: item for item in revisions}
            chapters: list[NovelExportChapter] = []
            for volume in story_map.volumes:
                for chapter in volume.get("chapters", []):
                    chapter_id = str(chapter.get("id"))
                    revision = by_chapter.get(chapter_id)
                    if revision is None:
                        continue
                    blocks = tuple(
                        NovelBlock.model_validate(block) for block in revision.blocks
                    )
                    translated_title = next(
                        (
                            block.text
                            for block in blocks
                            if block.type == "heading" and block.text.strip()
                        ),
                        str(chapter.get("title") or ""),
                    )
                    chapters.append(
                        NovelExportChapter(
                            volume_title=str(volume.get("title") or project.name),
                            chapter_title=translated_title,
                            blocks=tuple(
                                block
                                for block in blocks
                                if not (
                                    block.type == "heading"
                                    and block.text == translated_title
                                )
                            ),
                        )
                    )
        if not chapters:
            raise HTTPException(409, "请至少完成一章翻译后再导出译文")
        artifact = render_novel_docx(
            project_name=project.name, chapters=tuple(chapters)
        )
        revision_documents = _translation_documents(revisions)
        await deliveries.record(
            tenant_id=tid,
            project_id=project_id,
            domain="translation",
            stage="export",
            kind="translation_export_manifest",
            idempotency_key=f"translation-export:{_translation_hash(revision_documents)}",
            payload={
                "chapter_ids": [str(item["chapter_id"]) for item in revision_documents],
                "source_project_id": source_id,
                "target_language": str(project.direction.get("target_language") or ""),
            },
            artifact=artifact,
        )
        filename = f"translation-{project.id}.docx"
        return Response(
            artifact,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/projects/{project_id}/versions")
    async def create_translation_version(
        project_id: str,
        body: CreateTranslationVersionRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != tid
                or project.medium != ProjectMedium.TRANSLATION
            ):
                raise HTTPException(404, "翻译项目不存在")
            revisions = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            )
            if not revisions:
                raise HTTPException(409, "请至少完成一章翻译后再保存版本")
            documents = _translation_documents(revisions)
            version = int(
                await session.scalar(
                    select(func.coalesce(func.max(ProjectSnapshotModel.version), 0))
                    .where(ProjectSnapshotModel.project_id == project_id)
                )
                or 0
            ) + 1
            previous = (
                await session.scalars(
                    select(ProjectSnapshotModel)
                    .where(
                        ProjectSnapshotModel.project_id == project_id,
                        ProjectSnapshotModel.medium == "translation",
                    )
                    .order_by(ProjectSnapshotModel.version.desc())
                )
            ).first()
            snapshot = ProjectSnapshotModel(
                tenant_id=tid,
                project_id=project_id,
                medium="translation",
                version=version,
                name=body.name.strip(),
                scope=[str(item["chapter_id"]) for item in documents],
                word_count=sum(
                    len(str(block.get("text", "")))
                    for item in documents
                    for block in item["blocks"]
                    if isinstance(block, dict)
                ),
                content_hash=_translation_hash(documents),
                base_snapshot_id=previous.id if previous else None,
            )
            session.add(snapshot)
            await session.flush()
            session.add(
                TranslationSnapshotContentModel(
                    snapshot_id=snapshot.id, documents=documents
                )
            )
            return {"id": snapshot.id, "version": version, "name": snapshot.name}

    @router.get("/projects/{project_id}/versions")
    async def list_translation_versions(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "翻译项目不存在")
            records = list(
                await session.scalars(
                    select(ProjectSnapshotModel)
                    .where(
                        ProjectSnapshotModel.project_id == project_id,
                        ProjectSnapshotModel.medium == "translation",
                    )
                    .order_by(ProjectSnapshotModel.version.desc())
                )
            )
            return [
                {
                    "id": item.id,
                    "version": item.version,
                    "name": item.name,
                    "chapter_count": len(item.scope),
                    "word_count": item.word_count,
                    "created_at": item.created_at,
                }
                for item in records
            ]

    @router.post("/projects/{project_id}/versions/{snapshot_id}/restore")
    async def restore_translation_version(
        project_id: str,
        snapshot_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            snapshot = await session.get(ProjectSnapshotModel, snapshot_id)
            content = await session.get(TranslationSnapshotContentModel, snapshot_id)
            if (
                project is None
                or project.tenant_id != tid
                or snapshot is None
                or snapshot.project_id != project_id
                or snapshot.medium != "translation"
                or content is None
            ):
                raise HTTPException(404, "译文历史版本不存在")
            current = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            )
            for item in current:
                item.status = NovelRevisionStatus.SUPERSEDED
            for document in content.documents:
                chapter_id = str(document["chapter_id"])
                number = int(
                    await session.scalar(
                        select(
                            func.coalesce(
                                func.max(NovelDocumentRevisionModel.revision_number), 0
                            )
                        ).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.chapter_id == chapter_id,
                        )
                    )
                    or 0
                ) + 1
                session.add(
                    NovelDocumentRevisionModel(
                        project_id=project_id,
                        chapter_id=chapter_id,
                        blocks=document["blocks"],
                        status=NovelRevisionStatus.ADOPTED,
                        source="translation_snapshot",
                        revision_number=number,
                        idempotency_key=(
                            f"translation:restore:{snapshot_id}:{chapter_id}:{uuid4().hex[:8]}"
                        ),
                    )
                )
            return {"status": "restored", "version": snapshot.version}

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
            records = list(
                await session.scalars(
                    select(TranslationGlossaryTermModel)
                    .where(TranslationGlossaryTermModel.project_id == project_id)
                    .order_by(
                        TranslationGlossaryTermModel.status.desc(),
                        TranslationGlossaryTermModel.source_term,
                    )
                )
            )
            pending_counts = dict(
                (
                    await session.execute(
                        select(
                            TranslationCorrectionModel.term_id,
                            func.count(TranslationCorrectionModel.id),
                        )
                        .where(
                            TranslationCorrectionModel.project_id == project_id,
                            TranslationCorrectionModel.status == "pending",
                        )
                        .group_by(TranslationCorrectionModel.term_id)
                    )
                ).all()
            )
        return {
            "source_language": str((project.direction or {}).get("source_language") or ""),
            "target_language": str((project.direction or {}).get("target_language") or ""),
            "entries": [
                {
                    "id": item.id,
                    "source_term": item.source_term,
                    "target_term": item.target_term,
                    "status": item.status,
                    "source": item.source,
                    "pending_corrections": int(pending_counts.get(item.id, 0)),
                }
                for item in records
            ],
            "terms": {
                item.source_term: item.target_term
                for item in records
                if item.status == "confirmed" and item.target_term
            },
        }

    @router.put("/projects/{project_id}/glossary/{term_id}")
    async def update_glossary_endpoint(
        project_id: str,
        term_id: str,
        body: GlossaryTermRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "翻译项目不存在")
            term = await session.get(TranslationGlossaryTermModel, term_id)
            if term is None or term.project_id != project_id:
                raise HTTPException(404, "术语不存在")
            conflict = (
                await session.scalars(
                    select(TranslationGlossaryTermModel).where(
                        TranslationGlossaryTermModel.project_id == project_id,
                        TranslationGlossaryTermModel.source_term == body.source_term.strip(),
                        TranslationGlossaryTermModel.id != term_id,
                    )
                )
            ).one_or_none()
            if conflict:
                raise HTTPException(409, "源术语已经存在")
            previous_target = term.target_term
            required_target = body.target_term.strip()
            if (
                previous_target
                and required_target
                and previous_target != required_target
            ):
                revisions = list(
                    await session.scalars(
                        select(NovelDocumentRevisionModel).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.status
                            == NovelRevisionStatus.ADOPTED,
                        )
                    )
                )
                pending_items = list(
                    await session.scalars(
                        select(TranslationCorrectionModel).where(
                            TranslationCorrectionModel.term_id == term_id,
                            TranslationCorrectionModel.status == "pending",
                        )
                    )
                )
                pending_by_chapter = {
                    item.chapter_id: item for item in pending_items
                }
                for revision in revisions:
                    revision_text = "\n".join(
                        str(block.get("text", ""))
                        for block in revision.blocks
                        if isinstance(block, dict)
                    )
                    pending = pending_by_chapter.get(revision.chapter_id)
                    if pending is not None:
                        pending.required_target = required_target
                    elif previous_target in revision_text:
                        session.add(
                            TranslationCorrectionModel(
                                id=uuid4().hex,
                                project_id=project_id,
                                term_id=term_id,
                                chapter_id=revision.chapter_id,
                                previous_target=previous_target,
                                required_target=required_target,
                                status="pending",
                            )
                        )
            term.source_term = body.source_term.strip()
            term.target_term = required_target
            term.status = body.status
            term.source = "manual"
            return {"id": term.id, "status": term.status}

    @router.post("/projects/{project_id}/glossary/corrections/apply")
    async def apply_glossary_corrections(
        project_id: str,
        body: ApplyGlossaryCorrectionsRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        """Apply queued terminology changes as new chapter revisions."""
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "翻译项目不存在")
            query = select(TranslationCorrectionModel).where(
                TranslationCorrectionModel.project_id == project_id,
                TranslationCorrectionModel.status == "pending",
            )
            if body.term_id:
                query = query.where(
                    TranslationCorrectionModel.term_id == body.term_id
                )
            corrections = list(await session.scalars(query))
            by_chapter: dict[str, list[TranslationCorrectionModel]] = {}
            for correction in corrections:
                by_chapter.setdefault(correction.chapter_id, []).append(correction)

            updated_chapters = 0
            applied_replacements = 0
            for chapter_id, chapter_corrections in by_chapter.items():
                current = (
                    await session.scalars(
                        select(NovelDocumentRevisionModel).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.chapter_id == chapter_id,
                            NovelDocumentRevisionModel.status
                            == NovelRevisionStatus.ADOPTED,
                        )
                    )
                ).one_or_none()
                if current is None:
                    continue
                blocks = [dict(block) for block in current.blocks]
                changed = False
                for correction in chapter_corrections:
                    replacement_used = False
                    for block in blocks:
                        text = str(block.get("text", ""))
                        if correction.previous_target in text:
                            block["text"] = text.replace(
                                correction.previous_target,
                                correction.required_target,
                            )
                            replacement_used = True
                            changed = True
                    if replacement_used:
                        applied_replacements += 1
                    correction.status = "resolved"
                if not changed:
                    continue
                revision_number = int(
                    await session.scalar(
                        select(
                            func.coalesce(
                                func.max(
                                    NovelDocumentRevisionModel.revision_number
                                ),
                                0,
                            )
                        ).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.chapter_id == chapter_id,
                        )
                    )
                    or 0
                ) + 1
                current.status = NovelRevisionStatus.SUPERSEDED
                session.add(
                    NovelDocumentRevisionModel(
                        project_id=project_id,
                        chapter_id=chapter_id,
                        blocks=blocks,
                        status=NovelRevisionStatus.ADOPTED,
                        source="glossary_correction",
                        revision_number=revision_number,
                        base_revision_id=current.id,
                        idempotency_key=(
                            f"translation:correction:{chapter_id}:{uuid4().hex}"
                        ),
                    )
                )
                updated_chapters += 1
            return {
                "updated_chapters": updated_chapters,
                "applied_replacements": applied_replacements,
            }

    @router.post("/projects/{project_id}/glossary")
    async def create_glossary_term(
        project_id: str,
        body: GlossaryTermRequest,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tid:
                raise HTTPException(404, "翻译项目不存在")
            existing = (
                await session.scalars(
                    select(TranslationGlossaryTermModel).where(
                        TranslationGlossaryTermModel.project_id == project_id,
                        TranslationGlossaryTermModel.source_term == body.source_term.strip(),
                    )
                )
            ).one_or_none()
            if existing:
                existing.target_term = body.target_term.strip()
                existing.status = body.status
                existing.source = "manual"
                return {"id": existing.id, "status": existing.status}
            term = TranslationGlossaryTermModel(
                id=uuid4().hex,
                project_id=project_id,
                source_term=body.source_term.strip(),
                target_term=body.target_term.strip(),
                status=body.status,
                source="manual",
            )
            session.add(term)
            return {"id": term.id, "status": term.status}

    @router.delete("/projects/{project_id}/glossary/{term_id}", status_code=204)
    async def delete_glossary_term(
        project_id: str,
        term_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            term = await session.get(TranslationGlossaryTermModel, term_id)
            if (
                project is None
                or project.tenant_id != tid
                or term is None
                or term.project_id != project_id
            ):
                raise HTTPException(404, "术语不存在")
            await session.delete(term)

    @router.post("/documents")
    async def upload_and_translate(
        file: UploadFile,
        target_language: str = Form(...),
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ):
        """Upload a document (TXT/PDF/DOCX), extract text, create translation project."""
        import uuid
        from os import path

        context = await auth.validate_access(access_token)
        tid = str(context.tenant_id)

        raw = await file.read(settings.upload_max_file_bytes + 1)
        if len(raw) > settings.upload_max_file_bytes:
            raise HTTPException(413, "file is too large")
        filename = _validate_upload_filename(file.filename)
        if len(filename) > 255:
            raise HTTPException(400, "invalid file name")
        ext = _detect_extension(filename, file.content_type)
        text = _extract_uploaded_text(raw, ext, filename)

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
        project_name = path.splitext(filename)[0] or "translation"
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
