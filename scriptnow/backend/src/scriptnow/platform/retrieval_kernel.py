from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol

from scriptnow.platform.context_retrieval import (
    ContextPack,
    ContextRequest,
    EvidenceRef,
    RetrievalManifestPayload,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
    RetrievalStopReason,
)


@dataclass(frozen=True, slots=True)
class ContextSeed:
    """Deterministic domain context assembled before any probabilistic retrieval."""

    task_contract: dict[str, object]
    canonical_facts: tuple[dict[str, object], ...] = ()
    latest_revisions: tuple[dict[str, object], ...] = ()
    domain_state: dict[str, object] = field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = ()
    coverage: dict[str, float] = field(default_factory=dict)
    source_versions: dict[str, object] = field(default_factory=dict)
    omissions: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalBatch:
    evidence: tuple[EvidenceRef, ...] = ()
    source_versions: dict[str, object] = field(default_factory=dict)
    graph_paths: tuple[dict[str, object], ...] = ()
    omissions: tuple[dict[str, object], ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    context_pack: ContextPack
    manifest: RetrievalManifestPayload


class ContextAdapter(Protocol):
    """Domain boundary: each product decides its facts, queries, and state shape."""

    domain: str

    async def canonical_context(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
    ) -> ContextSeed: ...

    def plan_queries(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        *,
        missing_dimensions: tuple[str, ...],
        iteration: int,
    ) -> tuple[RetrievalQuery, ...]: ...


class Retriever(Protocol):
    """Evidence provider. Implementations may wrap lexical, graph, TM, or external search."""

    name: str
    mode: RetrievalMode

    async def retrieve(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        query: RetrievalQuery,
    ) -> RetrievalBatch: ...


class RetrievalCoordinator:
    """Policy-bounded retrieval loop with deterministic fusion and explicit failure."""

    def __init__(self, retrievers: tuple[Retriever, ...]) -> None:
        self._retrievers = retrievers

    async def retrieve(
        self,
        *,
        request: ContextRequest,
        policy: RetrievalPolicy,
        adapter: ContextAdapter,
    ) -> RetrievalResult:
        if adapter.domain != request.domain:
            raise ValueError("context adapter domain does not match request domain")
        unknown_dimensions = set(policy.coverage_requirements) - set(
            request.required_dimensions
        )
        if unknown_dimensions:
            raise ValueError("coverage policy contains unrequested dimensions")
        started = time.monotonic()
        try:
            async with asyncio.timeout(policy.timeout_seconds):
                return await self._retrieve(
                    request=request,
                    policy=policy,
                    adapter=adapter,
                    started=started,
                )
        except TimeoutError:
            seed = ContextSeed(
                task_contract={
                    "domain": request.domain,
                    "stage": request.stage,
                    "operation": request.operation,
                    "unit_ref": request.unit_ref,
                },
                omissions=({"reason": "canonical_context_timeout"},),
            )
            return self._result(
                request=request,
                policy=policy,
                seed=seed,
                evidence=seed.evidence,
                queries=(),
                source_versions=seed.source_versions,
                graph_paths=(),
                omissions=(*seed.omissions, {"reason": "retrieval_timeout"}),
                excluded=(),
                coverage=self._coverage(request, seed.coverage, seed.evidence),
                conflicts=(),
                input_tokens=0,
                output_tokens=0,
                stop_reason=RetrievalStopReason.TIMEOUT,
                started=started,
            )

    async def _retrieve(
        self,
        *,
        request: ContextRequest,
        policy: RetrievalPolicy,
        adapter: ContextAdapter,
        started: float,
    ) -> RetrievalResult:
        seed = await adapter.canonical_context(request, policy)
        evidence: list[EvidenceRef] = []
        source_versions = dict(seed.source_versions)
        queries: list[RetrievalQuery] = []
        graph_paths: list[dict[str, object]] = []
        omissions = list(seed.omissions)
        excluded: list[dict[str, object]] = []
        input_tokens = 0
        output_tokens = 0
        stop_reason = RetrievalStopReason.POLICY_LIMIT
        self._append_evidence(
            evidence,
            seed.evidence,
            policy=policy,
            source_versions=source_versions,
            excluded=excluded,
        )

        coverage = self._coverage(request, seed.coverage, evidence)
        if self._coverage_met(policy, coverage):
            stop_reason = RetrievalStopReason.COVERAGE_MET
        else:
            for iteration in range(1, policy.max_iterations + 1):
                missing = self._missing_dimensions(policy, coverage)
                planned = adapter.plan_queries(
                    request,
                    policy,
                    missing_dimensions=missing,
                    iteration=iteration,
                )
                if any(
                    set(query.dimensions) - set(request.required_dimensions)
                    for query in planned
                ):
                    raise ValueError("retrieval query contains unrequested dimensions")
                planned = tuple(
                    query
                    for query in planned
                    if query.iteration == iteration
                    and query.mode in policy.retrieval_modes
                    and (query.mode != RetrievalMode.EXTERNAL or policy.external_research_enabled)
                )
                queries.extend(planned)
                if not planned:
                    stop_reason = RetrievalStopReason.UNAVAILABLE
                    break
                successful_batch = False
                for query in planned:
                    compatible = tuple(
                        retriever
                        for retriever in self._retrievers
                        if retriever.mode == query.mode
                    )
                    if not compatible:
                        omissions.append(
                            {
                                "reason": "retriever_unavailable",
                                "mode": query.mode.value,
                                "iteration": iteration,
                            }
                        )
                        continue
                    for retriever in compatible:
                        try:
                            batch = await retriever.retrieve(request, policy, query)
                        except Exception as error:  # retriever boundary records, never conceals
                            omissions.append(
                                {
                                    "reason": "retriever_failed",
                                    "retriever": retriever.name,
                                    "mode": query.mode.value,
                                    "error_type": type(error).__name__,
                                    "iteration": iteration,
                                }
                            )
                            continue
                        successful_batch = True
                        input_tokens += batch.input_tokens
                        output_tokens += batch.output_tokens
                        graph_paths.extend(batch.graph_paths)
                        omissions.extend(batch.omissions)
                        self._append_evidence(
                            evidence,
                            batch.evidence,
                            policy=policy,
                            source_versions=source_versions,
                            excluded=excluded,
                        )
                        for source_key, version in batch.source_versions.items():
                            existing = source_versions.setdefault(source_key, version)
                            if existing != version:
                                omissions.append(
                                    {
                                        "reason": "source_version_conflict",
                                        "source": source_key,
                                        "expected": existing,
                                        "received": version,
                                    }
                                )
                coverage = self._coverage(request, seed.coverage, evidence)
                if self._coverage_met(policy, coverage):
                    stop_reason = RetrievalStopReason.COVERAGE_MET
                    break
                if not successful_batch:
                    stop_reason = RetrievalStopReason.UNAVAILABLE
                    break

        evidence = self._rank(evidence, policy)
        conflicts = self._conflicts(evidence)
        if conflicts and policy.conflict_policy == "block":
            stop_reason = RetrievalStopReason.CONFLICT
        elif not self._coverage_met(policy, coverage):
            stop_reason = (
                RetrievalStopReason.INSUFFICIENT_COVERAGE
                if stop_reason == RetrievalStopReason.POLICY_LIMIT
                else stop_reason
            )
        return self._result(
            request=request,
            policy=policy,
            seed=seed,
            evidence=tuple(evidence),
            queries=tuple(queries),
            source_versions=source_versions,
            graph_paths=tuple(graph_paths),
            omissions=tuple(omissions),
            excluded=tuple(excluded),
            coverage=coverage,
            conflicts=conflicts,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
            started=started,
        )

    @staticmethod
    def _append_evidence(
        evidence: list[EvidenceRef],
        incoming: tuple[EvidenceRef, ...],
        *,
        policy: RetrievalPolicy,
        source_versions: dict[str, object],
        excluded: list[dict[str, object]],
    ) -> None:
        known_refs = {item.ref_id for item in evidence}
        known_digests = {item.content_digest for item in evidence}
        used_tokens = sum(item.token_count for item in evidence)
        for item in incoming:
            source_key = f"{item.source_type}:{item.source_id}"
            expected_version = source_versions.get(source_key)
            if item.source_type not in policy.allowed_sources:
                excluded.append({"ref_id": item.ref_id, "reason": "source_not_allowed"})
            elif expected_version is not None and expected_version != item.source_version:
                excluded.append({"ref_id": item.ref_id, "reason": "stale_source_version"})
            elif item.ref_id in known_refs or item.content_digest in known_digests:
                excluded.append({"ref_id": item.ref_id, "reason": "duplicate"})
            elif used_tokens + item.token_count > policy.token_limit:
                excluded.append({"ref_id": item.ref_id, "reason": "token_limit"})
            else:
                evidence.append(item)
                known_refs.add(item.ref_id)
                known_digests.add(item.content_digest)
                used_tokens += item.token_count

    @staticmethod
    def _coverage(
        request: ContextRequest,
        seed_coverage: dict[str, float],
        evidence: list[EvidenceRef] | tuple[EvidenceRef, ...],
    ) -> dict[str, float]:
        coverage = {
            dimension: float(seed_coverage.get(dimension, 0))
            for dimension in request.required_dimensions
        }
        for item in evidence:
            contribution = item.metadata.get("coverage", {})
            for dimension in item.dimensions:
                if dimension in coverage:
                    value = contribution.get(dimension, 1.0) if isinstance(contribution, dict) else 1.0
                    coverage[dimension] = max(coverage[dimension], float(value))
        return coverage

    @staticmethod
    def _coverage_met(policy: RetrievalPolicy, coverage: dict[str, float]) -> bool:
        return all(
            coverage.get(dimension, 0) >= required
            for dimension, required in policy.coverage_requirements.items()
        )

    @staticmethod
    def _missing_dimensions(
        policy: RetrievalPolicy, coverage: dict[str, float]
    ) -> tuple[str, ...]:
        return tuple(
            dimension
            for dimension, required in policy.coverage_requirements.items()
            if coverage.get(dimension, 0) < required
        )

    @staticmethod
    def _rank(evidence: list[EvidenceRef], policy: RetrievalPolicy) -> list[EvidenceRef]:
        source_rank = {source: rank for rank, source in enumerate(policy.allowed_sources)}
        mode_rank = {mode: rank for rank, mode in enumerate(policy.retrieval_modes)}
        return sorted(
            evidence,
            key=lambda item: (
                source_rank.get(item.source_type, len(source_rank)),
                min((mode_rank.get(mode, len(mode_rank)) for mode in item.retrieval_modes), default=0),
                -(item.score or 0),
                item.ref_id,
            ),
        )

    @staticmethod
    def _conflicts(evidence: list[EvidenceRef]) -> tuple[dict[str, object], ...]:
        grouped: dict[str, list[EvidenceRef]] = {}
        for item in evidence:
            if item.fact_key:
                grouped.setdefault(item.fact_key, []).append(item)
        return tuple(
            {
                "fact_key": fact_key,
                "ref_ids": [item.ref_id for item in items],
                "content_digests": sorted({item.content_digest for item in items}),
            }
            for fact_key, items in sorted(grouped.items())
            if len({item.content_digest for item in items}) > 1
        )

    @staticmethod
    def _result(
        *,
        request: ContextRequest,
        policy: RetrievalPolicy,
        seed: ContextSeed,
        evidence: tuple[EvidenceRef, ...],
        queries: tuple[RetrievalQuery, ...],
        source_versions: dict[str, object],
        graph_paths: tuple[dict[str, object], ...],
        omissions: tuple[dict[str, object], ...],
        excluded: tuple[dict[str, object], ...],
        coverage: dict[str, float],
        conflicts: tuple[dict[str, object], ...],
        input_tokens: int,
        output_tokens: int,
        stop_reason: RetrievalStopReason,
        started: float,
    ) -> RetrievalResult:
        provenance = {
            "source_versions": source_versions,
            "query_count": len(queries),
            "stop_reason": stop_reason.value,
        }
        pack = ContextPack(
            task_contract=seed.task_contract,
            canonical_facts=seed.canonical_facts,
            latest_revisions=seed.latest_revisions,
            domain_state=seed.domain_state,
            evidence=evidence,
            conflicts=conflicts,
            omissions=omissions,
            provenance=provenance,
        )
        manifest = RetrievalManifestPayload(
            request=request,
            policy=policy,
            source_versions=source_versions,
            queries=queries,
            hit_refs=evidence,
            graph_paths=graph_paths,
            excluded_refs=excluded,
            coverage=coverage,
            conflicts=conflicts,
            omissions=omissions,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            stop_reason=stop_reason,
        )
        return RetrievalResult(context_pack=pack, manifest=manifest)
