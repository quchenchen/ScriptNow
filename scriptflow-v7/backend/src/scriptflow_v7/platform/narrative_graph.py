from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    NarrativeEdgeModel,
    NarrativeIndexModel,
    NarrativeIndexStatus,
    NarrativeNodeModel,
    NarrativeSummaryModel,
    NarrativeTextUnitModel,
    ProjectMedium,
    ProjectModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)
from scriptflow_v7.platform.narrative_graph_schema import (
    canonical_node_type,
    canonical_relation_type,
)


class NarrativeGraphError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticUnit:
    ordinal: int
    chapter_key: str
    chapter_title: str
    start_char: int
    end_char: int
    content: str
    contextual_header: str


@dataclass(frozen=True, slots=True)
class NarrativeHit:
    unit_id: str
    chapter_title: str
    ordinal: int
    content: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NarrativeNodeInput:
    node_key: str
    node_type: str
    name: str
    aliases: tuple[str, ...]
    description: str
    attributes: dict[str, object]
    evidence_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NarrativeEdgeInput:
    edge_key: str
    edge_type: str
    source_node_key: str
    target_node_key: str
    description: str
    evidence_unit_ids: tuple[str, ...]
    confidence: int
    inference: bool = False


@dataclass(frozen=True, slots=True)
class NarrativeSummaryInput:
    summary_key: str
    level: str
    title: str
    content: str
    child_unit_ids: tuple[str, ...] = ()
    child_summary_ids: tuple[str, ...] = ()
    evidence_node_ids: tuple[str, ...] = ()


_CHAPTER_PATTERNS = (
    re.compile(r"^chapter\s+([0-9ivxlcdm]+)(?:\s*[:.\-–—]\s*|\s+)?(.*)$", re.I),
    re.compile(
        r"^第\s*([0-9一二三四五六七八九十百千零〇两]+)\s*[章节回卷](?:\s*[:：.\-—]\s*)?(.*)$"
    ),
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9']+|[\u4e00-\u9fff]", re.I)


def segment_novel_text(text: str, *, target_characters: int = 2400) -> list[SemanticUnit]:
    """Split on paragraph and chapter boundaries; never cut through a paragraph."""
    if target_characters < 600:
        raise ValueError("target_characters must be at least 600")
    paragraphs = [(match.start(), match.group().strip()) for match in re.finditer(r"[^\n]+", text)]
    paragraphs = [(offset, value) for offset, value in paragraphs if value]
    if not paragraphs:
        return []

    units: list[SemanticUnit] = []
    chapter_number = 0
    chapter_key = "front-matter"
    chapter_title = "Front matter"
    buffer: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        start = buffer[0][0]
        content = "\n".join(value for _, value in buffer)
        units.append(
            SemanticUnit(
                ordinal=len(units),
                chapter_key=chapter_key,
                chapter_title=chapter_title,
                start_char=start,
                end_char=buffer[-1][0] + len(buffer[-1][1]),
                content=content,
                contextual_header=f"{chapter_title} · passage {len(units) + 1}",
            )
        )
        buffer = []

    for offset, paragraph in paragraphs:
        heading = _chapter_heading(paragraph)
        if heading is not None:
            flush()
            chapter_number += 1
            chapter_key = f"chapter-{heading[0] or chapter_number}"
            chapter_title = paragraph[:300]
            continue
        prospective = sum(len(value) + 1 for _, value in buffer) + len(paragraph)
        if buffer and prospective > target_characters:
            flush()
        buffer.append((offset, paragraph))
    flush()
    return units


class NarrativeGraphService:
    """Lightweight narrative GraphRAG persistence and hybrid retrieval."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def build_index(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_file_id: str,
        parsed_text: str,
        target_characters: int = 2400,
    ) -> NarrativeIndexModel:
        units = segment_novel_text(parsed_text, target_characters=target_characters)
        if not units:
            raise NarrativeGraphError("source contains no indexable narrative units")
        source_hash = hashlib.sha256(parsed_text.encode()).hexdigest()
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            source = await session.get(WorkspaceFileModel, source_file_id)
            if (
                project is None
                or project.tenant_id != tenant_id
                or project.medium != ProjectMedium.NOVEL
                or source is None
                or source.tenant_id != tenant_id
                or source.project_id != project_id
                or source.status != WorkspaceFileStatus.READY
            ):
                raise NarrativeGraphError("source is outside ready novel workspace")
            existing = (
                await session.scalars(
                    select(NarrativeIndexModel)
                    .where(
                        NarrativeIndexModel.source_file_id == source_file_id,
                        NarrativeIndexModel.source_hash == source_hash,
                        NarrativeIndexModel.status == NarrativeIndexStatus.READY,
                    )
                    .order_by(NarrativeIndexModel.version.desc())
                )
            ).first()
            if existing is not None:
                return existing
            version = (
                int(
                    await session.scalar(
                        select(func.max(NarrativeIndexModel.version)).where(
                            NarrativeIndexModel.source_file_id == source_file_id
                        )
                    )
                    or 0
                )
                + 1
            )
            index = NarrativeIndexModel(
                tenant_id=tenant_id,
                project_id=project_id,
                source_file_id=source_file_id,
                version=version,
                status=NarrativeIndexStatus.BUILDING,
                config={
                    "segmenter": "chapter-paragraph-v1",
                    "target_characters": target_characters,
                },
                source_hash=source_hash,
            )
            session.add(index)
            await session.flush()
            session.add_all(
                [
                    NarrativeTextUnitModel(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        index_id=index.id,
                        source_file_id=source_file_id,
                        ordinal=unit.ordinal,
                        chapter_key=unit.chapter_key,
                        chapter_title=unit.chapter_title,
                        start_char=unit.start_char,
                        end_char=unit.end_char,
                        content=unit.content,
                        contextual_header=unit.contextual_header,
                        content_hash=hashlib.sha256(unit.content.encode()).hexdigest(),
                    )
                    for unit in units
                ]
            )
            index.status = NarrativeIndexStatus.READY
            await session.flush()
            return index

    async def record_node(
        self,
        *,
        tenant_id: str,
        index_id: str,
        item: NarrativeNodeInput,
    ) -> NarrativeNodeModel:
        if not all((item.node_key.strip(), item.node_type.strip(), item.name.strip())):
            raise NarrativeGraphError("node key, type and name are required")
        try:
            node_type = canonical_node_type(item.node_type).value
        except ValueError as error:
            raise NarrativeGraphError(str(error)) from error
        async with self.database.session() as session:
            index = await self._index(session, tenant_id, index_id)
            await self._validate_units(session, index, item.evidence_unit_ids)
            existing = (
                await session.scalars(
                    select(NarrativeNodeModel).where(
                        NarrativeNodeModel.index_id == index.id,
                        NarrativeNodeModel.node_key == item.node_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                existing.node_type = node_type
                existing.aliases = list(dict.fromkeys([*existing.aliases, *item.aliases]))
                existing.evidence_unit_ids = list(
                    dict.fromkeys([*existing.evidence_unit_ids, *item.evidence_unit_ids])
                )
                if len(item.description) > len(existing.description):
                    existing.description = item.description
                await session.flush()
                return existing
            node = NarrativeNodeModel(
                index_id=index.id,
                node_key=item.node_key,
                node_type=node_type,
                name=item.name,
                aliases=list(dict.fromkeys(item.aliases)),
                description=item.description,
                attributes=item.attributes,
                evidence_unit_ids=list(dict.fromkeys(item.evidence_unit_ids)),
            )
            session.add(node)
            await session.flush()
            return node

    async def record_edge(
        self,
        *,
        tenant_id: str,
        index_id: str,
        item: NarrativeEdgeInput,
    ) -> NarrativeEdgeModel:
        if not 0 <= item.confidence <= 100:
            raise NarrativeGraphError("edge confidence must be between 0 and 100")
        try:
            edge_type = canonical_relation_type(item.edge_type).value
        except ValueError as error:
            raise NarrativeGraphError(str(error)) from error
        async with self.database.session() as session:
            index = await self._index(session, tenant_id, index_id)
            await self._validate_units(session, index, item.evidence_unit_ids)
            nodes = list(
                (
                    await session.scalars(
                        select(NarrativeNodeModel).where(
                            NarrativeNodeModel.index_id == index.id,
                            NarrativeNodeModel.node_key.in_(
                                (item.source_node_key, item.target_node_key)
                            ),
                        )
                    )
                ).all()
            )
            by_key = {node.node_key: node for node in nodes}
            if set(by_key) != {item.source_node_key, item.target_node_key}:
                raise NarrativeGraphError("edge references unknown narrative nodes")
            existing = (
                await session.scalars(
                    select(NarrativeEdgeModel).where(
                        NarrativeEdgeModel.index_id == index.id,
                        NarrativeEdgeModel.edge_key == item.edge_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                existing.edge_type = edge_type
                existing.evidence_unit_ids = list(
                    dict.fromkeys([*existing.evidence_unit_ids, *item.evidence_unit_ids])
                )
                existing.confidence = max(existing.confidence, item.confidence)
                existing.inference = existing.inference and item.inference
                await session.flush()
                return existing
            edge = NarrativeEdgeModel(
                index_id=index.id,
                edge_key=item.edge_key,
                edge_type=edge_type,
                source_node_id=by_key[item.source_node_key].id,
                target_node_id=by_key[item.target_node_key].id,
                description=item.description,
                evidence_unit_ids=list(dict.fromkeys(item.evidence_unit_ids)),
                confidence=item.confidence,
                inference=item.inference,
            )
            session.add(edge)
            await session.flush()
            return edge

    async def record_summary(
        self,
        *,
        tenant_id: str,
        index_id: str,
        item: NarrativeSummaryInput,
    ) -> NarrativeSummaryModel:
        if not all((item.summary_key.strip(), item.level.strip(), item.title.strip())):
            raise NarrativeGraphError("summary key, level and title are required")
        async with self.database.session() as session:
            index = await self._index(session, tenant_id, index_id)
            await self._validate_units(session, index, item.child_unit_ids)
            summaries = set(
                await session.scalars(
                    select(NarrativeSummaryModel.id).where(
                        NarrativeSummaryModel.index_id == index.id,
                        NarrativeSummaryModel.id.in_(item.child_summary_ids),
                    )
                )
            )
            nodes = set(
                await session.scalars(
                    select(NarrativeNodeModel.id).where(
                        NarrativeNodeModel.index_id == index.id,
                        NarrativeNodeModel.id.in_(item.evidence_node_ids),
                    )
                )
            )
            if summaries != set(item.child_summary_ids) or nodes != set(item.evidence_node_ids):
                raise NarrativeGraphError("summary provenance is outside narrative index")
            existing = (
                await session.scalars(
                    select(NarrativeSummaryModel).where(
                        NarrativeSummaryModel.index_id == index.id,
                        NarrativeSummaryModel.summary_key == item.summary_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return existing
            summary = NarrativeSummaryModel(
                index_id=index.id,
                summary_key=item.summary_key,
                level=item.level,
                title=item.title,
                content=item.content,
                child_unit_ids=list(dict.fromkeys(item.child_unit_ids)),
                child_summary_ids=list(dict.fromkeys(item.child_summary_ids)),
                evidence_node_ids=list(dict.fromkeys(item.evidence_node_ids)),
            )
            session.add(summary)
            await session.flush()
            return summary

    async def retrieve(
        self,
        *,
        tenant_id: str,
        index_id: str,
        query: str,
        semantic_scores: dict[str, float] | None = None,
        limit: int = 8,
    ) -> list[NarrativeHit]:
        if not query.strip() or not 1 <= limit <= 30:
            return []
        async with self.database.session() as session:
            index = await session.get(NarrativeIndexModel, index_id)
            if index is None or index.tenant_id != tenant_id:
                raise NarrativeGraphError("narrative index does not exist in tenant")
            units = list(
                (
                    await session.scalars(
                        select(NarrativeTextUnitModel)
                        .where(NarrativeTextUnitModel.index_id == index_id)
                        .order_by(NarrativeTextUnitModel.ordinal)
                    )
                ).all()
            )
            nodes = list(
                (
                    await session.scalars(
                        select(NarrativeNodeModel).where(NarrativeNodeModel.index_id == index_id)
                    )
                ).all()
            )
            edges = list(
                (
                    await session.scalars(
                        select(NarrativeEdgeModel).where(NarrativeEdgeModel.index_id == index_id)
                    )
                ).all()
            )

        query_terms = _tokens(query)
        bm25 = _bm25_scores(units, query_terms)
        ranked: list[tuple[str, list[str]]] = []
        ranked.append(("bm25", sorted(bm25, key=bm25.get, reverse=True)))
        if semantic_scores:
            valid_semantic = {key: value for key, value in semantic_scores.items() if key in bm25}
            ranked.append(
                ("semantic", sorted(valid_semantic, key=valid_semantic.get, reverse=True))
            )

        graph_units: list[str] = []
        matched_node_ids = {
            node.id for node in nodes if query_terms & _tokens(" ".join([node.name, *node.aliases]))
        }
        expanded = set(matched_node_ids)
        for edge in edges:
            if edge.source_node_id in matched_node_ids or edge.target_node_id in matched_node_ids:
                expanded.update((edge.source_node_id, edge.target_node_id))
                graph_units.extend(edge.evidence_unit_ids)
        for node in nodes:
            if node.id in expanded:
                graph_units.extend(node.evidence_unit_ids)
        if graph_units:
            ranked.append(("graph", list(dict.fromkeys(graph_units))))

        scores: defaultdict[str, float] = defaultdict(float)
        reasons: defaultdict[str, list[str]] = defaultdict(list)
        for channel, ordered_ids in ranked:
            for rank, unit_id in enumerate(ordered_ids, start=1):
                scores[unit_id] += 1.0 / (60 + rank)
                reasons[unit_id].append(channel)
        by_id = {unit.id: unit for unit in units}
        ordered = sorted(scores, key=scores.get, reverse=True)[:limit]
        return [
            NarrativeHit(
                unit_id=unit_id,
                chapter_title=by_id[unit_id].chapter_title,
                ordinal=by_id[unit_id].ordinal,
                content=by_id[unit_id].content,
                score=scores[unit_id],
                reasons=tuple(reasons[unit_id]),
            )
            for unit_id in ordered
            if unit_id in by_id
        ]

    @staticmethod
    async def _index(session, tenant_id: str, index_id: str) -> NarrativeIndexModel:
        index = await session.get(NarrativeIndexModel, index_id)
        if index is None or index.tenant_id != tenant_id:
            raise NarrativeGraphError("narrative index does not exist in tenant")
        return index

    @staticmethod
    async def _validate_units(session, index: NarrativeIndexModel, unit_ids) -> None:
        unique = set(unit_ids)
        if not unique:
            return
        found = set(
            await session.scalars(
                select(NarrativeTextUnitModel.id).where(
                    NarrativeTextUnitModel.index_id == index.id,
                    NarrativeTextUnitModel.id.in_(unique),
                )
            )
        )
        if found != unique:
            raise NarrativeGraphError("narrative provenance references unknown text units")


def _chapter_heading(paragraph: str) -> tuple[str, str] | None:
    if len(paragraph) > 180:
        return None
    for pattern in _CHAPTER_PATTERNS:
        if match := pattern.match(paragraph.strip()):
            return match.group(1), match.group(2).strip()
    return None


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_PATTERN.findall(value)}


def _bm25_scores(
    units: list[NarrativeTextUnitModel], query_terms: set[str], *, k1: float = 1.5, b: float = 0.75
) -> dict[str, float]:
    documents = [
        list(_TOKEN_PATTERN.findall(f"{unit.contextual_header} {unit.content}".casefold()))
        for unit in units
    ]
    average_length = sum(map(len, documents)) / max(len(documents), 1)
    document_frequency = Counter(
        term for document in documents for term in set(document) if term in query_terms
    )
    scores: dict[str, float] = {}
    for unit, document in zip(units, documents, strict=True):
        frequencies = Counter(document)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            inverse_document_frequency = math.log(
                1
                + (len(documents) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * len(document) / max(average_length, 1))
            score += inverse_document_frequency * frequency * (k1 + 1) / denominator
        scores[unit.id] = score
    return scores
