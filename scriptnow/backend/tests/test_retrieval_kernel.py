from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from scriptnow.platform.context_retrieval import (
    ContextRequest,
    EvidenceRef,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
    RetrievalStopReason,
)
from scriptnow.platform.retrieval_kernel import (
    ContextSeed,
    RetrievalBatch,
    RetrievalCoordinator,
)


def _request(*, dimensions: tuple[str, ...] = ("character", "continuity")) -> ContextRequest:
    return ContextRequest(
        tenant_id="tenant",
        project_id="project",
        domain="novel",
        stage="chapter",
        operation="novel.chapter.generate",
        unit_ref="chapter-1",
        required_dimensions=dimensions,
        risk_level="normal",
        policy_ref="policy-v1",
    )


def _policy(
    *,
    max_iterations: int = 2,
    conflict_policy: str = "surface",
    token_limit: int = 100,
) -> RetrievalPolicy:
    return RetrievalPolicy(
        allowed_sources=("project_facts", "uploaded_source"),
        retrieval_modes=(RetrievalMode.CANONICAL, RetrievalMode.LEXICAL),
        coverage_requirements={"character": 1.0, "continuity": 1.0},
        token_limit=token_limit,
        timeout_seconds=2,
        max_iterations=max_iterations,
        conflict_policy=conflict_policy,
        external_research_enabled=False,
    )


def _evidence(
    ref_id: str,
    *,
    source_type: str = "uploaded_source",
    source_id: str = "source-1",
    source_version: str = "v1",
    content: str | None = None,
    dimensions: tuple[str, ...] = ("character",),
    token_count: int = 4,
    fact_key: str | None = None,
    mode: RetrievalMode = RetrievalMode.LEXICAL,
) -> EvidenceRef:
    excerpt = content or ref_id
    return EvidenceRef(
        ref_id=ref_id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        locator={"ref": ref_id},
        content_digest=hashlib.sha256(excerpt.encode()).hexdigest(),
        score=1,
        retrieval_modes=(mode,),
        excerpt=excerpt,
        dimensions=dimensions,
        token_count=token_count,
        fact_key=fact_key,
    )


class FakeAdapter:
    domain = "novel"

    def __init__(self, seed: ContextSeed) -> None:
        self.seed = seed
        self.iterations: list[int] = []

    async def canonical_context(
        self, request: ContextRequest, policy: RetrievalPolicy
    ) -> ContextSeed:
        return self.seed

    def plan_queries(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        *,
        missing_dimensions: tuple[str, ...],
        iteration: int,
    ) -> tuple[RetrievalQuery, ...]:
        self.iterations.append(iteration)
        return (
            RetrievalQuery(
                query=" ".join(missing_dimensions),
                iteration=iteration,
                mode=RetrievalMode.LEXICAL,
                purpose=" ".join(missing_dimensions),
                dimensions=missing_dimensions,
            ),
        )


@dataclass
class FakeRetriever:
    batches: tuple[RetrievalBatch, ...]
    name: str = "fake"
    mode: RetrievalMode = RetrievalMode.LEXICAL
    calls: int = 0

    async def retrieve(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        query: RetrievalQuery,
    ) -> RetrievalBatch:
        batch = self.batches[min(self.calls, len(self.batches) - 1)]
        self.calls += 1
        return batch


@pytest.mark.asyncio
async def test_deterministic_context_precedes_retrieval_and_stops_on_coverage() -> None:
    canonical = _evidence(
        "canonical",
        source_type="project_facts",
        source_id="facts",
        dimensions=("character",),
        mode=RetrievalMode.CANONICAL,
    )
    retrieved = _evidence("retrieved", dimensions=("continuity",))
    adapter = FakeAdapter(
        ContextSeed(
            task_contract={"operation": "write"},
            evidence=(canonical,),
            source_versions={
                "project_facts:facts": "v1",
                "uploaded_source:source-1": "v1",
            },
        )
    )
    retriever = FakeRetriever((RetrievalBatch(evidence=(retrieved,)),))

    result = await RetrievalCoordinator((retriever,)).retrieve(
        request=_request(), policy=_policy(), adapter=adapter
    )

    assert [item.ref_id for item in result.context_pack.evidence] == [
        "canonical",
        "retrieved",
    ]
    assert result.manifest.coverage == {"character": 1.0, "continuity": 1.0}
    assert result.manifest.stop_reason == RetrievalStopReason.COVERAGE_MET
    assert retriever.calls == 1


@pytest.mark.asyncio
async def test_loop_uses_policy_limit_and_does_not_invent_completion() -> None:
    adapter = FakeAdapter(ContextSeed(task_contract={"operation": "write"}))
    retriever = FakeRetriever((RetrievalBatch(),))

    result = await RetrievalCoordinator((retriever,)).retrieve(
        request=_request(), policy=_policy(max_iterations=3), adapter=adapter
    )

    assert adapter.iterations == [1, 2, 3]
    assert result.manifest.stop_reason == RetrievalStopReason.INSUFFICIENT_COVERAGE
    assert result.manifest.coverage == {"character": 0.0, "continuity": 0.0}


@pytest.mark.asyncio
async def test_stale_duplicate_and_over_budget_evidence_are_excluded() -> None:
    duplicate = _evidence("duplicate", content="same")
    adapter = FakeAdapter(
        ContextSeed(
            task_contract={"operation": "write"},
            evidence=(duplicate,),
            source_versions={"uploaded_source:source-1": "v1"},
        )
    )
    batch = RetrievalBatch(
        evidence=(
            _evidence("duplicate-copy", content="same"),
            _evidence("stale", source_version="v0"),
            _evidence("large", token_count=200),
        )
    )
    result = await RetrievalCoordinator((FakeRetriever((batch,)),)).retrieve(
        request=_request(), policy=_policy(token_limit=10), adapter=adapter
    )

    reasons = {item["reason"] for item in result.manifest.excluded_refs}
    assert reasons == {"duplicate", "stale_source_version", "token_limit"}
    assert [item.ref_id for item in result.context_pack.evidence] == ["duplicate"]


@pytest.mark.asyncio
async def test_conflict_is_explicit_and_can_block() -> None:
    adapter = FakeAdapter(ContextSeed(task_contract={"operation": "write"}))
    batch = RetrievalBatch(
        evidence=(
            _evidence("claim-a", content="alive", fact_key="character:status"),
            _evidence("claim-b", content="dead", fact_key="character:status"),
        )
    )
    result = await RetrievalCoordinator((FakeRetriever((batch,)),)).retrieve(
        request=_request(), policy=_policy(conflict_policy="block"), adapter=adapter
    )

    assert result.manifest.stop_reason == RetrievalStopReason.CONFLICT
    assert result.context_pack.conflicts[0]["fact_key"] == "character:status"


@pytest.mark.asyncio
async def test_retriever_failure_is_recorded_as_unavailable() -> None:
    class BrokenRetriever(FakeRetriever):
        async def retrieve(self, request, policy, query):
            raise RuntimeError("provider is down")

    result = await RetrievalCoordinator((BrokenRetriever((RetrievalBatch(),)),)).retrieve(
        request=_request(),
        policy=_policy(),
        adapter=FakeAdapter(ContextSeed(task_contract={"operation": "write"})),
    )

    assert result.manifest.stop_reason == RetrievalStopReason.UNAVAILABLE
    assert result.manifest.omissions[0]["reason"] == "retriever_failed"
    assert result.manifest.omissions[0]["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_same_request_replays_same_versioned_evidence() -> None:
    evidence = _evidence("stable", dimensions=("character", "continuity"))
    seed = ContextSeed(
        task_contract={"operation": "write"},
        source_versions={"uploaded_source:source-1": "v1"},
    )
    coordinator = RetrievalCoordinator(
        (FakeRetriever((RetrievalBatch(evidence=(evidence,)),)),)
    )

    first = await coordinator.retrieve(
        request=_request(), policy=_policy(), adapter=FakeAdapter(seed)
    )
    second = await coordinator.retrieve(
        request=_request(), policy=_policy(), adapter=FakeAdapter(seed)
    )

    assert first.manifest.hit_refs == second.manifest.hit_refs
    assert first.manifest.source_versions == second.manifest.source_versions
    assert first.manifest.queries == second.manifest.queries
    assert first.context_pack == second.context_pack
