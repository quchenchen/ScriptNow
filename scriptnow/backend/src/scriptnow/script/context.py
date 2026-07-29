from __future__ import annotations

import hashlib
import json

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
from scriptnow.script.service import ScriptService

SCRIPT_DIMENSIONS = frozenset(
    {"scene_contract", "continuity", "blueprint", "source_fidelity"}
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


class ScriptSceneContextAdapter:
    """Script-only adapter: screenplay continuity remains outside Novel and platform."""

    domain = "script"

    def __init__(self, database: Database, *, token_counter) -> None:
        self._database = database
        self._service = ScriptService(database)
        self._token_counter = token_counter

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed:
        del policy
        if not request.unit_ref:
            raise ValueError("script scene context requires a scene unit_ref")
        async with self._database.session() as session:
            project = await session.get(ProjectModel, request.project_id)
            if project is None or project.tenant_id != request.tenant_id:
                raise ValueError("script project is unavailable")
            direction = dict(project.direction or {})
        context = await self._service.context_pack(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            scene_id=request.unit_ref,
        )
        scene = dict(context.get("scene") or {})
        scene_ordinal = int(context.get("scene_ordinal") or 0)
        anchors = list(context.get("anchors") or [])
        adopted_scenes = list(context.get("adopted_scenes") or [])
        evidence: list[EvidenceRef] = []
        source_versions: dict[str, object] = {}
        if scene:
            scene_digest = _digest(scene)
            scene_text = json.dumps(scene, ensure_ascii=False, sort_keys=True)
            story_map_id = str(context.get("story_map_id") or request.project_id)
            story_map_version = int(context.get("story_map_version") or 0)
            evidence.append(
                EvidenceRef(
                    ref_id=f"script_story_map:{story_map_id}:{request.unit_ref}",
                    source_type="script_story_map",
                    source_id=story_map_id,
                    source_version=f"version:{story_map_version}",
                    locator={
                        "scene_id": request.unit_ref,
                        "scene_ordinal": scene_ordinal,
                    },
                    content_digest=scene_digest,
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=scene_text,
                    dimensions=("scene_contract",),
                    token_count=self._token_counter(scene_text),
                )
            )
            source_versions[f"script_story_map:{story_map_id}"] = (
                f"version:{story_map_version}"
            )
        if anchors:
            anchor_digest = _digest(anchors)
            anchor_text = json.dumps(anchors, ensure_ascii=False, sort_keys=True)
            evidence.append(
                EvidenceRef(
                    ref_id=f"script_blueprint:{request.project_id}:{anchor_digest[:16]}",
                    source_type="script_blueprint",
                    source_id=request.project_id,
                    source_version=f"sha256:{anchor_digest}",
                    locator={"scene_id": request.unit_ref},
                    content_digest=anchor_digest,
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=anchor_text,
                    dimensions=("blueprint", "scene_contract"),
                    token_count=self._token_counter(anchor_text),
                )
            )
            source_versions[f"script_blueprint:{request.project_id}"] = (
                f"sha256:{anchor_digest}"
            )
        latest_revisions = []
        for revision in adopted_scenes:
            revision_id = str(revision["revision_id"])
            revision_text = json.dumps(
                revision.get("blocks") or [], ensure_ascii=False, sort_keys=True
            )
            revision_digest = _digest(revision.get("blocks") or [])
            evidence.append(
                EvidenceRef(
                    ref_id=f"script_revision:{revision_id}",
                    source_type="script_revision",
                    source_id=revision_id,
                    source_version=f"sha256:{revision_digest}",
                    locator={"scene_id": revision["scene_id"]},
                    content_digest=revision_digest,
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=revision_text,
                    dimensions=("continuity",),
                    token_count=self._token_counter(revision_text),
                )
            )
            source_versions[f"script_revision:{revision_id}"] = (
                f"sha256:{revision_digest}"
            )
            latest_revisions.append(dict(revision))

        requested = set(request.required_dimensions)
        coverage: dict[str, float] = {}
        if "scene_contract" in requested and scene:
            coverage["scene_contract"] = 1.0
        if "blueprint" in requested and anchors:
            coverage["blueprint"] = 1.0
        if "continuity" in requested and (scene_ordinal == 1 or adopted_scenes):
            coverage["continuity"] = 1.0
        return ContextSeed(
            task_contract={
                "domain": self.domain,
                "stage": request.stage,
                "operation": request.operation,
                "unit_ref": request.unit_ref,
                "creative_language": direction.get("creative_language"),
                "script_format": direction.get("script_format"),
            },
            canonical_facts=(
                ({"kind": "scene_contract", "scene": scene},)
                + tuple({"kind": "blueprint_anchor", **anchor} for anchor in anchors)
            ),
            latest_revisions=tuple(latest_revisions),
            domain_state={
                "scene_id": request.unit_ref,
                "scene_ordinal": scene_ordinal,
                "project_direction": direction,
            },
            evidence=tuple(evidence),
            coverage=coverage,
            source_versions=source_versions,
            omissions=(
                ({"reason": "scene_blueprint_anchors_empty"},)
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
            dimension for dimension in missing_dimensions if dimension in SCRIPT_DIMENSIONS
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
                        purpose="fill screenplay scene context gaps",
                        dimensions=dimensions,
                    ),
                )
        return ()
