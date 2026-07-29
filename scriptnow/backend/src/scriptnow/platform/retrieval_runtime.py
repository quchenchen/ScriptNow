from __future__ import annotations

from scriptnow.platform.config import Settings
from scriptnow.platform.context_retrieval import (
    RetrievalMode,
    RetrievalPolicy,
)
from scriptnow.platform.context_retrieval_service import ContextRetrievalService
from scriptnow.platform.database import Database
from scriptnow.platform.rag import RagService
from scriptnow.platform.retrieval_kernel import RetrievalCoordinator
from scriptnow.platform.retrievers import LexicalRagRetriever, NarrativeGraphRetriever


def estimate_tokens(text: str) -> int:
    """Cheap deterministic accounting; provider usage remains the billing authority."""

    return max(1, (len(text) + 3) // 4)


def retrieval_service(
    database: Database,
    settings: Settings,
) -> ContextRetrievalService:
    coordinator = RetrievalCoordinator(
        (
            LexicalRagRetriever(
                RagService(database),
                source_type="workspace_source",
                result_limit=settings.context_retrieval_lexical_result_limit,
                token_counter=estimate_tokens,
            ),
            NarrativeGraphRetriever(
                database,
                source_type="narrative_graph_source",
                result_limit=settings.context_retrieval_graph_result_limit,
                token_counter=estimate_tokens,
            ),
        )
    )
    return ContextRetrievalService(database, coordinator)


def retrieval_policy(
    settings: Settings,
    *,
    allowed_sources: tuple[str, ...],
    coverage_requirements: dict[str, float],
    modes: tuple[RetrievalMode, ...] = (
        RetrievalMode.LEXICAL,
        RetrievalMode.NARRATIVE_GRAPH,
    ),
) -> RetrievalPolicy:
    return RetrievalPolicy(
        allowed_sources=allowed_sources,
        retrieval_modes=modes,
        coverage_requirements=coverage_requirements,
        token_limit=settings.context_retrieval_token_limit,
        timeout_seconds=settings.context_retrieval_timeout_seconds,
        max_iterations=settings.context_retrieval_max_iterations,
        conflict_policy=settings.context_retrieval_conflict_policy,
        external_research_enabled=False,
    )
