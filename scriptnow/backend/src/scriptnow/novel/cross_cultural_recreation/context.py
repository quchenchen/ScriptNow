from __future__ import annotations

import hashlib
import json

from scriptnow.novel.cross_cultural_recreation.domain import (
    RecreationArtifactKind,
    RecreationArtifactStatus,
)
from scriptnow.novel.cross_cultural_recreation.service import (
    CrossCulturalRecreationService,
)
from scriptnow.platform.context_retrieval import (
    ContextRequest,
    EvidenceRef,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
)
from scriptnow.platform.database import Database
from scriptnow.platform.retrieval_kernel import ContextSeed

RECREATION_DIMENSIONS = frozenset(
    {
        "source_structure",
        "source_characters",
        "source_causality",
        "source_culture",
        "source_protection",
        "source_genes",
        "source_fidelity",
        "target_contract",
        "cultural_mapping",
        "protection_decisions",
        "package_scope",
        "continuity",
    }
)

RECREATION_ARTIFACT_DIMENSIONS = {
    RecreationArtifactKind.SOURCE_STORY_MODEL.value: ("source_genes",),
    RecreationArtifactKind.TARGET_STORY_CONTRACT.value: ("target_contract",),
    RecreationArtifactKind.RECREATION_STRATEGY.value: (
        "source_genes",
        "target_contract",
    ),
    RecreationArtifactKind.CULTURAL_MAPPING_SET.value: ("cultural_mapping",),
    RecreationArtifactKind.PROTECTION_CONFLICT_DECISION.value: (
        "protection_decisions",
    ),
    RecreationArtifactKind.PILOT.value: ("continuity", "target_contract"),
    RecreationArtifactKind.SCALE_PLAN.value: ("package_scope", "continuity"),
}

SOURCE_ANALYSIS_LAYERS = (
    (
        "source_structure",
        "story structure turning points opening escalation climax ending",
        "reconstruct the complete source story structure",
    ),
    (
        "source_characters",
        "protagonist desire need wound agency relationship change character arc",
        "trace character motivations relationships and arcs",
    ),
    (
        "source_causality",
        "cause consequence setup payoff reveal reversal dependency",
        "trace causal chains setup payoff and later constraints",
    ),
    (
        "source_culture",
        "family institution class custom daily life social norm cultural script",
        "identify culture-bound knowledge and social scripts",
    ),
    (
        "source_protection",
        "theme emotional promise moral dilemma ending cost invariant protect",
        "identify candidate story genes and protected elements",
    ),
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


class RecreationSourceAnalysisContextAdapter:
    """Layered source-work retrieval before a source story model exists."""

    domain = "recreation"

    def __init__(self, database: Database) -> None:
        self._service = CrossCulturalRecreationService(database)

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed:
        del policy
        record = await self._service.get(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
        )
        return ContextSeed(
            task_contract={
                "domain": self.domain,
                "stage": request.stage,
                "operation": request.operation,
                "source_language": record.source_language,
                "target_language": record.target_language,
                "target_market": record.target_market,
            },
            domain_state={
                "target_audience": record.target_audience,
                "distribution_context": record.distribution_context,
            },
        )

    def plan_queries(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        *,
        missing_dimensions: tuple[str, ...],
        iteration: int,
    ) -> tuple[RetrievalQuery, ...]:
        missing = set(missing_dimensions)
        modes = tuple(
            mode
            for mode in (RetrievalMode.LEXICAL, RetrievalMode.NARRATIVE_GRAPH)
            if mode in policy.retrieval_modes
        )
        if not modes:
            return ()
        mode = modes[min(iteration - 1, len(modes) - 1)]
        return tuple(
            RetrievalQuery(
                query=" ".join(
                    part
                    for part in (query, request.user_intent)
                    if part
                ),
                iteration=iteration,
                mode=mode,
                purpose=purpose,
                dimensions=(dimension,),
            )
            for dimension, query, purpose in SOURCE_ANALYSIS_LAYERS
            if dimension in missing
        )


class RecreationStageContextAdapter:
    """Stage-level adopted artifacts plus bounded source retrieval."""

    domain = "recreation"

    def __init__(
        self,
        database: Database,
        *,
        required_artifacts: tuple[RecreationArtifactKind, ...],
        token_counter,
    ) -> None:
        self._service = CrossCulturalRecreationService(database)
        self._required_artifacts = required_artifacts
        self._token_counter = token_counter

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed:
        del policy
        record = await self._service.get(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
        )
        artifacts = await self._service.artifacts(recreation_id=record.id)
        adopted = {
            str(item.kind): item
            for item in artifacts
            if str(item.status) == RecreationArtifactStatus.ADOPTED
        }
        missing = [
            kind.value for kind in self._required_artifacts if kind.value not in adopted
        ]
        if missing:
            raise ValueError(
                "recreation context is missing adopted artifacts: " + ", ".join(missing)
            )

        evidence: list[EvidenceRef] = []
        source_versions: dict[str, object] = {}
        canonical_facts: list[dict[str, object]] = []
        coverage: dict[str, float] = {}
        included_kinds = list(self._required_artifacts)
        for governance_kind in (
            RecreationArtifactKind.CULTURAL_MAPPING_SET,
            RecreationArtifactKind.PROTECTION_CONFLICT_DECISION,
        ):
            if governance_kind.value in adopted and governance_kind not in included_kinds:
                included_kinds.append(governance_kind)
        for kind in included_kinds:
            artifact = adopted[kind.value]
            payload = dict(artifact.payload)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            dimensions = RECREATION_ARTIFACT_DIMENSIONS[kind.value]
            evidence.append(
                EvidenceRef(
                    ref_id=f"recreation_artifact:{artifact.id}",
                    source_type="recreation_artifact",
                    source_id=artifact.id,
                    source_version=f"version:{artifact.version}",
                    locator={"kind": kind.value},
                    content_digest=_digest(payload),
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=text,
                    dimensions=dimensions,
                    token_count=self._token_counter(text),
                )
            )
            source_versions[f"recreation_artifact:{artifact.id}"] = (
                f"version:{artifact.version}"
            )
            canonical_facts.append({"kind": kind.value, "payload": payload})
            coverage.update({dimension: 1.0 for dimension in dimensions})

        requested = set(request.required_dimensions)
        return ContextSeed(
            task_contract={
                "domain": self.domain,
                "stage": request.stage,
                "operation": request.operation,
                "source_language": record.source_language,
                "target_language": record.target_language,
                "target_market": record.target_market,
            },
            canonical_facts=tuple(canonical_facts),
            domain_state={
                "target_audience": record.target_audience,
                "distribution_context": record.distribution_context,
            },
            evidence=tuple(evidence),
            coverage={
                key: value for key, value in coverage.items() if key in requested
            },
            source_versions=source_versions,
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
            if dimension in RECREATION_DIMENSIONS
        )
        if not dimensions:
            return ()
        query_text = " ".join(
            part
            for part in (
                request.operation,
                request.unit_ref,
                request.user_intent,
            )
            if part
        )
        for mode in (RetrievalMode.LEXICAL, RetrievalMode.NARRATIVE_GRAPH):
            if mode in policy.retrieval_modes:
                return (
                    RetrievalQuery(
                        query=query_text,
                        iteration=iteration,
                        mode=mode,
                        purpose="fill cross-cultural recreation stage evidence gaps",
                        dimensions=dimensions,
                    ),
                )
        return ()


class RecreationUnitContextAdapter:
    """Cross-cultural recreation context; never reuses faithful translation semantics."""

    domain = "recreation"

    def __init__(self, database: Database, *, token_counter) -> None:
        self._service = CrossCulturalRecreationService(database)
        self._token_counter = token_counter

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed:
        del policy
        if not request.unit_ref:
            raise ValueError("recreation context requires a work-package unit_ref")
        record = await self._service.get(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
        )
        artifacts = await self._service.artifacts(recreation_id=record.id)
        adopted = {
            str(item.kind): item
            for item in artifacts
            if str(item.status) == RecreationArtifactStatus.ADOPTED
        }
        required = (
            RecreationArtifactKind.SOURCE_STORY_MODEL,
            RecreationArtifactKind.TARGET_STORY_CONTRACT,
            RecreationArtifactKind.RECREATION_STRATEGY,
            RecreationArtifactKind.PILOT,
            RecreationArtifactKind.SCALE_PLAN,
        )
        missing = [kind.value for kind in required if kind.value not in adopted]
        if missing:
            raise ValueError(
                "recreation context is missing adopted artifacts: " + ", ".join(missing)
            )
        scale_plan = dict(adopted[RecreationArtifactKind.SCALE_PLAN.value].payload)
        packages = [
            dict(item)
            for item in list(scale_plan.get("work_packages") or [])
            if isinstance(item, dict)
        ]
        package = next(
            (
                item
                for item in packages
                if str(item.get("order")) == request.unit_ref
            ),
            None,
        )
        if package is None:
            raise ValueError("recreation work package is outside the adopted scale plan")
        package_index = packages.index(package)
        prior_keys = {str(item.get("order")) for item in packages[:package_index]}
        units = await self._service.production_units(recreation_id=record.id)
        prior_units = [
            item
            for item in units
            if str(item.status) == RecreationArtifactStatus.ADOPTED
            and item.work_package_key in prior_keys
        ]

        evidence: list[EvidenceRef] = []
        source_versions: dict[str, object] = {}
        canonical_facts: list[dict[str, object]] = []
        included_kinds = list(required)
        for governance_kind in (
            RecreationArtifactKind.CULTURAL_MAPPING_SET,
            RecreationArtifactKind.PROTECTION_CONFLICT_DECISION,
        ):
            if governance_kind.value in adopted:
                included_kinds.append(governance_kind)
        for kind in included_kinds:
            artifact = adopted[kind.value]
            payload = dict(artifact.payload)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            digest = _digest(payload)
            evidence.append(
                EvidenceRef(
                    ref_id=f"recreation_artifact:{artifact.id}",
                    source_type="recreation_artifact",
                    source_id=artifact.id,
                    source_version=f"version:{artifact.version}",
                    locator={"kind": kind.value},
                    content_digest=digest,
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=text,
                    dimensions=RECREATION_ARTIFACT_DIMENSIONS[kind.value],
                    token_count=self._token_counter(text),
                )
            )
            source_versions[f"recreation_artifact:{artifact.id}"] = (
                f"version:{artifact.version}"
            )
            canonical_facts.append({"kind": kind.value, "payload": payload})
        for unit in prior_units:
            payload = dict(unit.payload)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            evidence.append(
                EvidenceRef(
                    ref_id=f"recreation_unit:{unit.id}",
                    source_type="recreation_unit",
                    source_id=unit.id,
                    source_version=f"version:{unit.version}",
                    locator={"work_package_key": unit.work_package_key},
                    content_digest=_digest(payload),
                    retrieval_modes=(RetrievalMode.CANONICAL,),
                    excerpt=text,
                    dimensions=("continuity",),
                    token_count=self._token_counter(text),
                )
            )
            source_versions[f"recreation_unit:{unit.id}"] = f"version:{unit.version}"

        requested = set(request.required_dimensions)
        coverage = {
            "source_genes": 1.0,
            "target_contract": 1.0,
            "package_scope": 1.0,
        }
        if RecreationArtifactKind.CULTURAL_MAPPING_SET.value in adopted:
            coverage["cultural_mapping"] = 1.0
        if RecreationArtifactKind.PROTECTION_CONFLICT_DECISION.value in adopted:
            coverage["protection_decisions"] = 1.0
        if package_index == 0 or prior_units:
            coverage["continuity"] = 1.0
        return ContextSeed(
            task_contract={
                "domain": self.domain,
                "stage": request.stage,
                "operation": request.operation,
                "unit_ref": request.unit_ref,
                "source_language": record.source_language,
                "target_language": record.target_language,
                "target_market": record.target_market,
            },
            canonical_facts=tuple(canonical_facts),
            latest_revisions=tuple(
                {
                    "work_package_key": item.work_package_key,
                    "unit_id": item.id,
                    "version": item.version,
                    "payload": dict(item.payload),
                }
                for item in prior_units
            ),
            domain_state={
                "current_work_package": package,
                "work_package_ordinal": package_index + 1,
                "work_package_count": len(packages),
            },
            evidence=tuple(evidence),
            coverage={
                key: value for key, value in coverage.items() if key in requested
            },
            source_versions=source_versions,
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
            if dimension in RECREATION_DIMENSIONS
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
                        purpose="fill cross-cultural recreation evidence gaps",
                        dimensions=dimensions,
                    ),
                )
        return ()
