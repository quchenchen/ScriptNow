from __future__ import annotations

from dataclasses import dataclass

from scriptnow.platform.context_retrieval import (
    ContextPack,
    ContextRequest,
    RetrievalManifestPayload,
    RetrievalPolicy,
)
from scriptnow.platform.database import Database
from scriptnow.platform.retrieval_kernel import (
    ContextAdapter,
    RetrievalCoordinator,
)
from scriptnow.platform.retrieval_manifest import RetrievalManifestStore


@dataclass(frozen=True, slots=True)
class PersistedRetrieval:
    manifest_id: str
    content_digest: str
    context_pack: ContextPack
    manifest: RetrievalManifestPayload


class ContextRetrievalService:
    """Run retrieval and persist its immutable manifest before Agent execution."""

    def __init__(
        self,
        database: Database,
        coordinator: RetrievalCoordinator,
        *,
        manifests: RetrievalManifestStore | None = None,
    ) -> None:
        self._database = database
        self._coordinator = coordinator
        self._manifests = manifests or RetrievalManifestStore()

    async def build(
        self,
        *,
        request: ContextRequest,
        policy: RetrievalPolicy,
        adapter: ContextAdapter,
    ) -> PersistedRetrieval:
        result = await self._coordinator.retrieve(
            request=request,
            policy=policy,
            adapter=adapter,
        )
        async with self._database.session() as session:
            stored = await self._manifests.create(session, payload=result.manifest)
            return PersistedRetrieval(
                manifest_id=stored.id,
                content_digest=stored.content_digest,
                context_pack=result.context_pack,
                manifest=result.manifest,
            )
