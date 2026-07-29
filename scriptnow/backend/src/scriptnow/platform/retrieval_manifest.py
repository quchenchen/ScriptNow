from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scriptnow.platform.context_manifest import content_digest
from scriptnow.platform.context_retrieval import RetrievalManifestPayload
from scriptnow.platform.models import CreativeRetrievalManifestModel


@dataclass(frozen=True, slots=True)
class RetrievalManifestView:
    id: str
    content_digest: str
    content: dict[str, object]
    source_versions: dict[str, object]


class RetrievalManifestStore:
    """Persist immutable retrieval evidence without owning domain retrieval logic."""

    async def create(
        self,
        session: AsyncSession,
        *,
        payload: RetrievalManifestPayload,
    ) -> CreativeRetrievalManifestModel:
        content = payload.model_dump(mode="json")
        digest = content_digest(content)
        request = payload.request
        existing = (
            await session.scalars(
                select(CreativeRetrievalManifestModel).where(
                    CreativeRetrievalManifestModel.tenant_id == request.tenant_id,
                    CreativeRetrievalManifestModel.project_id == request.project_id,
                    CreativeRetrievalManifestModel.content_digest == digest,
                )
            )
        ).one_or_none()
        if existing is not None:
            return existing
        manifest = CreativeRetrievalManifestModel(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            domain=request.domain,
            stage=request.stage,
            operation=request.operation,
            schema_version=payload.schema_version,
            content_digest=digest,
            content=content,
            source_versions=payload.source_versions,
        )
        session.add(manifest)
        await session.flush()
        return manifest

    async def load(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        manifest_id: str,
    ) -> RetrievalManifestView:
        manifest = await session.get(CreativeRetrievalManifestModel, manifest_id)
        if manifest is None or manifest.tenant_id != tenant_id:
            raise ValueError("retrieval manifest is outside tenant scope")
        if content_digest(manifest.content) != manifest.content_digest:
            raise ValueError("retrieval manifest digest does not match immutable content")
        return RetrievalManifestView(
            id=manifest.id,
            content_digest=manifest.content_digest,
            content=manifest.content,
            source_versions=manifest.source_versions,
        )
