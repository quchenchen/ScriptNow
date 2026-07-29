from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.platform.context_retrieval import (
    ContextRequest,
    EvidenceRef,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel
from scriptnow.platform.retrieval_kernel import ContextSeed
from scriptnow.translation.domain import TranslationGlossaryTermModel

TRANSLATION_DIMENSIONS = frozenset(
    {"source_fidelity", "terminology", "voice", "continuity"}
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _text(blocks: list[dict[str, object]]) -> str:
    return "\n".join(
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict) and block.get("text")
    )


class FaithfulTranslationContextAdapter:
    """Deterministic translation context; probabilistic retrieval only fills declared gaps."""

    domain = "translation"

    def __init__(self, database: Database, *, token_counter) -> None:
        self._database = database
        self._token_counter = token_counter

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed:
        del policy
        if not request.unit_ref:
            raise ValueError("translation context requires a chapter unit_ref")
        async with self._database.session() as session:
            project = await session.get(ProjectModel, request.project_id)
            if project is None or project.tenant_id != request.tenant_id:
                raise ValueError("translation project is unavailable")
            direction = dict(project.direction or {})
            source_project_id = str(direction.get("source_project_id") or "")
            source_project = await session.get(ProjectModel, source_project_id)
            if source_project is None or source_project.tenant_id != request.tenant_id:
                raise ValueError("translation source project is unavailable")
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(
                        NovelStoryMapModel.project_id == source_project_id
                    )
                )
            ).one_or_none()
            if story_map is None:
                raise ValueError("translation source StoryMap is unavailable")
            chapter_ids = [
                str(chapter.get("id"))
                for volume in story_map.volumes
                for chapter in volume.get("chapters", [])
            ]
            try:
                chapter_index = chapter_ids.index(request.unit_ref)
            except ValueError as error:
                raise ValueError("translation chapter is outside source StoryMap") from error
            source_revision = (
                await session.scalars(
                    select(NovelDocumentRevisionModel)
                    .where(
                        NovelDocumentRevisionModel.project_id == source_project_id,
                        NovelDocumentRevisionModel.chapter_id == request.unit_ref,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                    .order_by(NovelDocumentRevisionModel.revision_number.desc())
                )
            ).first()
            if source_revision is None:
                raise ValueError("translation source chapter has no adopted revision")
            glossary = tuple(
                (
                    await session.scalars(
                        select(TranslationGlossaryTermModel)
                        .where(
                            TranslationGlossaryTermModel.project_id == request.project_id,
                            TranslationGlossaryTermModel.status == "confirmed",
                            TranslationGlossaryTermModel.target_term != "",
                        )
                        .order_by(TranslationGlossaryTermModel.source_term)
                    )
                ).all()
            )
            prior_revision = None
            if chapter_index > 0:
                prior_revision = (
                    await session.scalars(
                        select(NovelDocumentRevisionModel)
                        .where(
                            NovelDocumentRevisionModel.project_id == request.project_id,
                            NovelDocumentRevisionModel.chapter_id
                            == chapter_ids[chapter_index - 1],
                            NovelDocumentRevisionModel.status
                            == NovelRevisionStatus.ADOPTED,
                        )
                        .order_by(NovelDocumentRevisionModel.revision_number.desc())
                    )
                ).first()

        source_blocks = list(source_revision.blocks)
        source_text = _text(source_blocks)
        glossary_payload = [
            {"source": term.source_term, "target": term.target_term} for term in glossary
        ]
        evidence = [
            EvidenceRef(
                ref_id=f"source_revision:{source_revision.id}",
                source_type="source_revision",
                source_id=source_revision.id,
                source_version=f"revision:{source_revision.revision_number}",
                locator={
                    "project_id": source_project_id,
                    "chapter_id": request.unit_ref,
                },
                content_digest=_digest(source_blocks),
                retrieval_modes=(RetrievalMode.CANONICAL,),
                excerpt=source_text,
                dimensions=("source_fidelity", "voice"),
                token_count=self._token_counter(source_text),
            )
        ]
        latest_revisions: list[dict[str, object]] = [
            {
                "role": "source",
                "chapter_id": request.unit_ref,
                "revision_id": source_revision.id,
                "revision_number": source_revision.revision_number,
                "blocks": source_blocks,
            }
        ]
        source_versions: dict[str, object] = {
            f"source_revision:{source_revision.id}": (
                f"revision:{source_revision.revision_number}"
            ),
            f"source_story_map:{story_map.id}": f"version:{story_map.version}",
        }
        if glossary_payload:
            glossary_digest = _digest(glossary_payload)
            evidence.append(
                EvidenceRef(
                    ref_id=f"translation_glossary:{request.project_id}:{glossary_digest[:16]}",
                    source_type="translation_glossary",
                    source_id=request.project_id,
                    source_version=f"sha256:{glossary_digest}",
                    locator={"term_count": len(glossary_payload)},
                    content_digest=glossary_digest,
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt="\n".join(
                        f"{item['source']} → {item['target']}" for item in glossary_payload
                    ),
                    dimensions=("terminology",),
                    token_count=sum(
                        self._token_counter(f"{item['source']} {item['target']}")
                        for item in glossary_payload
                    ),
                )
            )
            source_versions[f"translation_glossary:{request.project_id}"] = (
                f"sha256:{glossary_digest}"
            )
        if prior_revision is not None:
            prior_blocks = list(prior_revision.blocks)
            prior_text = _text(prior_blocks)
            evidence.append(
                EvidenceRef(
                    ref_id=f"prior_translation:{prior_revision.id}",
                    source_type="prior_translation",
                    source_id=prior_revision.id,
                    source_version=f"revision:{prior_revision.revision_number}",
                    locator={"chapter_id": prior_revision.chapter_id},
                    content_digest=_digest(prior_blocks),
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=prior_text,
                    dimensions=("voice", "continuity"),
                    token_count=self._token_counter(prior_text),
                )
            )
            latest_revisions.append(
                {
                    "role": "prior_translation",
                    "chapter_id": prior_revision.chapter_id,
                    "revision_id": prior_revision.id,
                    "revision_number": prior_revision.revision_number,
                    "blocks": prior_blocks,
                }
            )
            source_versions[f"prior_translation:{prior_revision.id}"] = (
                f"revision:{prior_revision.revision_number}"
            )

        requested = set(request.required_dimensions)
        coverage = {
            dimension: 1.0
            for dimension in requested
            if dimension in {"source_fidelity", "voice"}
        }
        if "terminology" in requested and glossary_payload:
            coverage["terminology"] = 1.0
        if "continuity" in requested and (chapter_index == 0 or prior_revision is not None):
            coverage["continuity"] = 1.0
        return ContextSeed(
            task_contract={
                "domain": self.domain,
                "stage": request.stage,
                "operation": request.operation,
                "unit_ref": request.unit_ref,
                "source_language": direction.get("source_language"),
                "target_language": direction.get("target_language"),
            },
            canonical_facts=(
                {
                    "kind": "confirmed_glossary",
                    "terms": glossary_payload,
                },
            ),
            latest_revisions=tuple(latest_revisions),
            domain_state={
                "source_project_id": source_project_id,
                "chapter_ordinal": chapter_index + 1,
                "chapter_count": len(chapter_ids),
            },
            evidence=tuple(evidence),
            coverage=coverage,
            source_versions=source_versions,
            omissions=(
                ({"reason": "confirmed_glossary_empty"},)
                if "terminology" in requested and not glossary_payload
                else ()
            ),
        )

    def plan_queries(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        *,
        missing_dimensions: tuple[str, ...],
        iteration: int,
    ) -> tuple[RetrievalQuery, ...]:
        dimensions = tuple(
            dimension
            for dimension in missing_dimensions
            if dimension in TRANSLATION_DIMENSIONS
        )
        if not dimensions:
            return ()
        query_text = " ".join(
            part for part in (request.unit_ref, request.user_intent) if part
        )
        for mode in (
            RetrievalMode.TRANSLATION_MEMORY,
            RetrievalMode.LEXICAL,
            RetrievalMode.NARRATIVE_GRAPH,
        ):
            if mode in policy.retrieval_modes:
                return (
                    RetrievalQuery(
                        query=query_text,
                        iteration=iteration,
                        mode=mode,
                        purpose="fill faithful translation context gaps",
                        dimensions=dimensions,
                    ),
                )
        return ()
