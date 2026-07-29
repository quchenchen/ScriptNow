import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import delete, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import RagChunkModel, WorkspaceFileModel, WorkspaceFileStatus


class RagError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RagHit:
    chunk_id: str
    source_file_id: str
    ordinal: int
    content: str
    score: int
    content_hash: str
    source_version: str


class RagService:
    def __init__(self, database: Database, *, chunk_characters: int = 800) -> None:
        if chunk_characters < 100:
            raise ValueError("chunk_characters must be at least 100")
        self.database = database
        self.chunk_characters = chunk_characters

    async def index_text(
        self, *, tenant_id: str, project_id: str, source_file_id: str, parsed_text: str
    ) -> int:
        async with self.database.session() as session:
            source = await session.get(WorkspaceFileModel, source_file_id)
            if (
                source is None
                or source.tenant_id != tenant_id
                or source.project_id != project_id
                or source.status != WorkspaceFileStatus.READY
            ):
                raise RagError("source is outside ready tenant workspace")
            await session.execute(
                delete(RagChunkModel).where(RagChunkModel.source_file_id == source_file_id)
            )
            chunks = self._chunks(parsed_text)
            session.add_all(
                [
                    RagChunkModel(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        source_file_id=source_file_id,
                        ordinal=index,
                        content=content,
                        content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    )
                    for index, content in enumerate(chunks)
                ]
            )
            return len(chunks)

    async def search(
        self, *, tenant_id: str, project_id: str, query: str, limit: int = 5
    ) -> list[RagHit]:
        terms = {term.casefold() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if term}
        if not terms:
            return []
        async with self.database.session() as session:
            rows = (
                await session.execute(
                    select(RagChunkModel, WorkspaceFileModel.sha256)
                    .join(WorkspaceFileModel, WorkspaceFileModel.id == RagChunkModel.source_file_id)
                    .where(
                        RagChunkModel.tenant_id == tenant_id,
                        RagChunkModel.project_id == project_id,
                    )
                )
            ).all()
            hits = []
            for chunk, source_sha256 in rows:
                normalized = chunk.content.casefold()
                score = sum(normalized.count(term) for term in terms)
                if score:
                    hits.append(
                        RagHit(
                            chunk.id,
                            chunk.source_file_id,
                            chunk.ordinal,
                            chunk.content,
                            score,
                            chunk.content_hash,
                            f"sha256:{source_sha256}",
                        )
                    )
            return sorted(hits, key=lambda hit: (-hit.score, hit.ordinal))[:limit]

    async def browse(
        self, *, tenant_id: str, project_id: str, limit: int = 5
    ) -> list[RagHit]:
        async with self.database.session() as session:
            rows = (
                await session.execute(
                    select(RagChunkModel, WorkspaceFileModel.sha256)
                    .join(WorkspaceFileModel, WorkspaceFileModel.id == RagChunkModel.source_file_id)
                    .where(
                        RagChunkModel.tenant_id == tenant_id,
                        RagChunkModel.project_id == project_id,
                    )
                    .order_by(RagChunkModel.source_file_id, RagChunkModel.ordinal)
                    .limit(limit)
                )
            ).all()
            return [
                RagHit(
                    chunk.id,
                    chunk.source_file_id,
                    chunk.ordinal,
                    chunk.content,
                    0,
                    chunk.content_hash,
                    f"sha256:{source_sha256}",
                )
                for chunk, source_sha256 in rows
            ]

    def _chunks(self, text: str) -> list[str]:
        normalized = text.strip()
        return [
            normalized[offset : offset + self.chunk_characters]
            for offset in range(0, len(normalized), self.chunk_characters)
        ]
