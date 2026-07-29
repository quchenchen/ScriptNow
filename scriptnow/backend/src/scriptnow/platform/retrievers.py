from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select

from scriptnow.platform.context_retrieval import (
    ContextRequest,
    EvidenceRef,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import NarrativeIndexModel, NarrativeIndexStatus
from scriptnow.platform.narrative_graph import NarrativeGraphService
from scriptnow.platform.rag import RagService
from scriptnow.platform.retrieval_kernel import RetrievalBatch

TokenCounter = Callable[[str], int]


class LexicalRagRetriever:
    """Expose the existing workspace lexical index through the shared retrieval protocol."""

    name = "workspace_lexical_rag"
    mode = RetrievalMode.LEXICAL

    def __init__(
        self,
        rag: RagService,
        *,
        source_type: str,
        result_limit: int,
        token_counter: TokenCounter,
    ) -> None:
        if not source_type:
            raise ValueError("source_type is required")
        if result_limit < 1:
            raise ValueError("result_limit must be positive")
        self._rag = rag
        self._source_type = source_type
        self._result_limit = result_limit
        self._token_counter = token_counter

    async def retrieve(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        query: RetrievalQuery,
    ) -> RetrievalBatch:
        if query.mode != self.mode:
            raise ValueError("lexical retriever received an incompatible query mode")
        project_ids = (request.project_id, *request.retrieval_project_ids)
        hits = []
        for project_id in project_ids:
            hits.extend(
                await self._rag.search(
                    tenant_id=request.tenant_id,
                    project_id=project_id,
                    query=query.query,
                    limit=self._result_limit,
                )
            )
        hits = sorted(
            {hit.chunk_id: hit for hit in hits}.values(),
            key=lambda hit: (-hit.score, hit.ordinal, hit.chunk_id),
        )[: self._result_limit]
        source_versions = {
            f"{self._source_type}:{hit.source_file_id}": hit.source_version for hit in hits
        }
        return RetrievalBatch(
            evidence=tuple(
                EvidenceRef(
                    ref_id=f"rag_chunk:{hit.chunk_id}",
                    source_type=self._source_type,
                    source_id=hit.source_file_id,
                    source_version=hit.source_version,
                    locator={"chunk_id": hit.chunk_id, "ordinal": hit.ordinal},
                    content_digest=hit.content_hash,
                    score=float(hit.score),
                    retrieval_modes=(RetrievalMode.LEXICAL,),
                    excerpt=hit.content,
                    dimensions=query.dimensions,
                    token_count=self._token_counter(hit.content),
                )
                for hit in hits
            ),
            source_versions=source_versions,
        )


class NarrativeGraphRetriever:
    """Use every current ready narrative index without making one domain own the kernel."""

    name = "narrative_graph"
    mode = RetrievalMode.NARRATIVE_GRAPH

    def __init__(
        self,
        database: Database,
        *,
        source_type: str,
        result_limit: int,
        token_counter: TokenCounter,
    ) -> None:
        if not source_type:
            raise ValueError("source_type is required")
        if result_limit < 1:
            raise ValueError("result_limit must be positive")
        self._database = database
        self._graphs = NarrativeGraphService(database)
        self._source_type = source_type
        self._result_limit = result_limit
        self._token_counter = token_counter

    async def retrieve(
        self,
        request: ContextRequest,
        policy: RetrievalPolicy,
        query: RetrievalQuery,
    ) -> RetrievalBatch:
        if query.mode != self.mode:
            raise ValueError("narrative graph retriever received an incompatible query mode")
        project_ids = (request.project_id, *request.retrieval_project_ids)
        async with self._database.session() as session:
            indexes = tuple(
                (
                    await session.scalars(
                        select(NarrativeIndexModel)
                        .where(
                            NarrativeIndexModel.tenant_id == request.tenant_id,
                            NarrativeIndexModel.project_id.in_(project_ids),
                            NarrativeIndexModel.status == NarrativeIndexStatus.READY,
                        )
                        .order_by(
                            NarrativeIndexModel.source_file_id,
                            NarrativeIndexModel.version.desc(),
                        )
                    )
                ).all()
            )
        latest_by_source: dict[str, NarrativeIndexModel] = {}
        for index in indexes:
            latest_by_source.setdefault(index.source_file_id, index)

        hits = []
        for index in latest_by_source.values():
            hits.extend(
                await self._graphs.retrieve(
                    tenant_id=request.tenant_id,
                    index_id=index.id,
                    query=query.query,
                    limit=self._result_limit,
                )
            )
        hits = sorted(hits, key=lambda item: (-item.score, item.ordinal, item.unit_id))[
            : self._result_limit
        ]
        return RetrievalBatch(
            evidence=tuple(
                EvidenceRef(
                    ref_id=f"narrative_unit:{hit.unit_id}",
                    source_type=self._source_type,
                    source_id=hit.source_file_id,
                    source_version=hit.source_version,
                    locator={
                        "index_id": hit.index_id,
                        "unit_id": hit.unit_id,
                        "chapter_title": hit.chapter_title,
                        "ordinal": hit.ordinal,
                    },
                    content_digest=hit.content_hash,
                    score=hit.score,
                    retrieval_modes=(RetrievalMode.NARRATIVE_GRAPH,),
                    excerpt=hit.content,
                    dimensions=query.dimensions,
                    token_count=self._token_counter(hit.content),
                    metadata={"reasons": hit.reasons},
                )
                for hit in hits
            ),
            source_versions={
                f"{self._source_type}:{index.source_file_id}": f"sha256:{index.source_hash}"
                for index in latest_by_source.values()
            },
            graph_paths=tuple(
                {
                    "index_id": hit.index_id,
                    "unit_id": hit.unit_id,
                    "reasons": hit.reasons,
                }
                for hit in hits
                if "graph" in hit.reasons
            ),
            omissions=(
                ()
                if latest_by_source
                else (
                    {
                        "reason": "narrative_index_unavailable",
                        "project_ids": project_ids,
                    },
                )
            ),
        )
