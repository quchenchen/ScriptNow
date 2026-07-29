from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.novel.service import NovelService
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

NOVEL_DIMENSIONS = frozenset(
    {
        "chapter_contract",
        "blueprint",
        "continuity",
        "character_state",
        "source_fidelity",
    }
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


class NovelChapterContextAdapter:
    """Novel-only adapter; screenplay and translation contracts never enter this boundary."""

    domain = "novel"

    def __init__(self, database: Database, *, token_counter) -> None:
        self._database = database
        self._service = NovelService(database)
        self._token_counter = token_counter

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed:
        del policy
        if not request.unit_ref:
            raise ValueError("novel chapter context requires a chapter unit_ref")
        async with self._database.session() as session:
            project = await session.get(ProjectModel, request.project_id)
            if project is None or project.tenant_id != request.tenant_id:
                raise ValueError("novel project is unavailable")
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(
                        NovelStoryMapModel.project_id == request.project_id
                    )
                )
            ).one_or_none()
            direction = dict(project.direction or {})
        if story_map is None:
            raise ValueError("novel StoryMap is unavailable")

        chapter_ids = [
            str(dict(chapter).get("id"))
            for volume in story_map.volumes
            for chapter in list(dict(volume).get("chapters") or [])
        ]
        try:
            chapter_index = chapter_ids.index(request.unit_ref)
        except ValueError as error:
            raise ValueError("novel chapter is outside the adopted StoryMap") from error
        chapter_ordinals = {
            chapter_id: ordinal for ordinal, chapter_id in enumerate(chapter_ids)
        }
        chapter = next(
            dict(chapter)
            for volume in story_map.volumes
            for chapter in list(dict(volume).get("chapters") or [])
            if str(dict(chapter).get("id")) == request.unit_ref
        )
        continuity = await self._service.context_pack(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            chapter_id=request.unit_ref,
        )
        anchors = list(continuity.get("anchors") or [])
        effective = [
            dict(item)
            for item in list(continuity.get("effective_chapters") or [])
            if chapter_ordinals.get(str(item.get("chapter_id")), len(chapter_ids))
            < chapter_index
        ]

        evidence: list[EvidenceRef] = []
        source_versions: dict[str, object] = {
            f"novel_story_map:{story_map.id}": f"version:{story_map.version}"
        }
        chapter_text = json.dumps(chapter, ensure_ascii=False, sort_keys=True)
        evidence.append(
            EvidenceRef(
                ref_id=f"novel_story_map:{story_map.id}:{request.unit_ref}",
                source_type="novel_story_map",
                source_id=story_map.id,
                source_version=f"version:{story_map.version}",
                locator={
                    "chapter_id": request.unit_ref,
                    "chapter_ordinal": chapter_index + 1,
                },
                content_digest=_digest(chapter),
                retrieval_modes=(RetrievalMode.CANONICAL,),
                excerpt=chapter_text,
                dimensions=("chapter_contract",),
                token_count=self._token_counter(chapter_text),
            )
        )
        if anchors:
            anchor_text = json.dumps(anchors, ensure_ascii=False, sort_keys=True)
            anchor_digest = _digest(anchors)
            evidence.append(
                EvidenceRef(
                    ref_id=f"novel_blueprint:{request.project_id}:{anchor_digest[:16]}",
                    source_type="novel_blueprint",
                    source_id=request.project_id,
                    source_version=f"sha256:{anchor_digest}",
                    locator={"chapter_id": request.unit_ref},
                    content_digest=anchor_digest,
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=anchor_text,
                    dimensions=("blueprint", "character_state"),
                    token_count=self._token_counter(anchor_text),
                )
            )
            source_versions[f"novel_blueprint:{request.project_id}"] = (
                f"sha256:{anchor_digest}"
            )
        for revision in effective:
            blocks = list(revision.get("blocks") or [])
            revision_text = json.dumps(blocks, ensure_ascii=False, sort_keys=True)
            revision_id = str(revision.get("revision_id"))
            revision_number = int(revision.get("revision_number") or 0)
            evidence.append(
                EvidenceRef(
                    ref_id=f"novel_revision:{revision_id}",
                    source_type="novel_revision",
                    source_id=revision_id,
                    source_version=f"revision:{revision_number}",
                    locator={"chapter_id": str(revision.get("chapter_id"))},
                    content_digest=_digest(blocks),
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=revision_text,
                    dimensions=("continuity", "character_state"),
                    token_count=self._token_counter(revision_text),
                )
            )
            source_versions[f"novel_revision:{revision_id}"] = (
                f"revision:{revision_number}"
            )

        requested = set(request.required_dimensions)
        coverage: dict[str, float] = {"chapter_contract": 1.0}
        if anchors:
            coverage["blueprint"] = 1.0
            coverage["character_state"] = 1.0
        if chapter_index == 0 or effective:
            coverage["continuity"] = 1.0
        return ContextSeed(
            task_contract={
                "domain": self.domain,
                "stage": request.stage,
                "operation": request.operation,
                "unit_ref": request.unit_ref,
                "creative_language": direction.get("language"),
            },
            canonical_facts=(
                ({"kind": "chapter_contract", "chapter": chapter},)
                + tuple({"kind": "blueprint_anchor", **anchor} for anchor in anchors)
            ),
            latest_revisions=tuple(effective),
            domain_state={
                "chapter_ordinal": chapter_index + 1,
                "chapter_count": len(chapter_ids),
                "project_direction": direction,
            },
            evidence=tuple(evidence),
            coverage={
                key: value for key, value in coverage.items() if key in requested
            },
            source_versions=source_versions,
            omissions=(
                ({"reason": "novel_blueprint_anchors_empty"},)
                if "blueprint" in requested and not anchors
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
            dimension for dimension in missing_dimensions if dimension in NOVEL_DIMENSIONS
        )
        if not dimensions:
            return ()
        query_text = " ".join(
            part for part in (request.unit_ref, request.user_intent) if part
        )
        for mode in (RetrievalMode.LEXICAL, RetrievalMode.NARRATIVE_GRAPH):
            if mode in policy.retrieval_modes:
                return (
                    RetrievalQuery(
                        query=query_text,
                        iteration=iteration,
                        mode=mode,
                        purpose="fill novel chapter context gaps",
                        dimensions=dimensions,
                    ),
                )
        return ()
