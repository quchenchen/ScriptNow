"""逐章创作图谱 (Creative Graph) — 区别于故事图谱 (Narrative Graph)。

故事图谱用于导入已有作品后一次性提取，输入是上传的 NarrativeTextUnit。
创作图谱用于原创写作中逐章增量更新，输入是采纳后的 NovelDocumentRevision。

章节采纳后自动后台提取人物、关系、事件、摘要；
积累的图谱注入 Writer 上下文，让后续章节全局感知存量资产。

内部索引 key: creative:{project_id}  ← 与用户创建的 NarrativeIndex 命名空间隔离。
"""

from __future__ import annotations

import json

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RunStatus
from scriptnow.platform.narrative_graph import (
    NarrativeEdgeInput,
    NarrativeGraphError,
    NarrativeGraphService,
    NarrativeNodeInput,
    NarrativeSummaryInput,
)
from scriptnow.platform.narrative_graph_schema import (
    NODE_TYPE_VALUES,
    RELATION_TYPE_VALUES,
    NarrativeNodeType,
    NarrativeRelationType,
    canonical_node_type,
    canonical_relation_type,
)
from scriptnow.platform.run_coordinator import RunCoordinator


class CreativeGraphError(RuntimeError):
    pass


# ── Payload schema (identical contract to NarrativeGraphExtractor) ────────


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=3, max_length=160)
    type: NarrativeNodeType
    name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=12)
    description: str = Field(min_length=1, max_length=1200)
    blocks_ordinals: list[int] = Field(min_length=1, max_length=20, alias="evidence_ordinals")

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> NarrativeNodeType:
        if not isinstance(value, str):
            raise ValueError("narrative node type must be a string")
        return canonical_node_type(value)


class _Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=3, max_length=180)
    type: NarrativeRelationType
    source: str = Field(min_length=3, max_length=160)
    target: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=1, max_length=1200)
    blocks_ordinals: list[int] = Field(min_length=1, max_length=20, alias="evidence_ordinals")
    confidence: int = Field(ge=0, le=100)
    inference: bool = False

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> NarrativeRelationType:
        if not isinstance(value, str):
            raise ValueError("edge type must be a string")
        return canonical_relation_type(value)


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_title: str = Field(min_length=1, max_length=300)
    chapter_summary: str = Field(min_length=1, max_length=1800)
    nodes: list[_Node] = Field(default_factory=list, max_length=40)
    edges: list[_Edge] = Field(default_factory=list, max_length=80)


# ── Extractor ────────────────────────────────────────────────────────────


class CreativeGraphExtractor:
    """Extract and persist a creative graph from adopted novel chapters."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.graphs = NarrativeGraphService(database)

    async def extract_chapter(
        self,
        *,
        tenant_id: str,
        project_id: str,
        chapter_id: str,
        chapter_title: str,
        blocks: list[dict[str, object]],
        idempotency_key: str,
    ) -> None:
        """Extract graph from a single adopted chapter revision."""
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise CreativeGraphError("project is outside tenant scope")

        status = await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        architect = dict(dict(status["roles"])["architect"])
        if not architect.get("connected"):
            raise CreativeGraphError(
                f"graph extraction runtime unavailable: {architect.get('reason') or 'unknown'}"
            )

        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=f"creative-graph:{chapter_id}:{idempotency_key}",
        )
        if run.status == RunStatus.QUEUED:
            await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)

        # Build the extraction source: block index → ordinal
        source_blocks: list[dict[str, object]] = []
        ordinal = 0
        for _idx, block in enumerate(blocks):
            block_type = str(block.get("type") or "prose")
            text = str(block.get("text") or "")
            # Only include readable narrative blocks (skip dividers without text)
            if block_type == "divider" and not text.strip():
                continue
            source_blocks.append({"ordinal": ordinal, "block_type": block_type, "text": text})
            ordinal += 1

        if not source_blocks:
            raise CreativeGraphError("chapter contains no extractable narrative blocks")

        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
                role="architect",
                stage_override="source-analysis",
                explicit_skill_keys=("novel-build-story-graph",),
                content=(
                    "Extract an evidence-grounded narrative graph for this chapter. "
                    "Return JSON only: "
                    '{"chapter_title":"...","chapter_summary":"what changes and remains unresolved",'
                    f'"nodes":[{{"key":"type:stable-key","type":"{"|".join(NODE_TYPE_VALUES)}",'
                    '"name":"...","aliases":[],"description":"...","evidence_ordinals":[0]}}],'
                    f'"edges":[{{"key":"...","type":"{"|".join(RELATION_TYPE_VALUES)}",'
                    '"source":"node-key","target":"node-key","description":"...",'
                    '"evidence_ordinals":[0],"confidence":90,"inference":false}]}. '
                    "Every ordinal must be valid. Do not quote long prose.\n"
                    + json.dumps(source_blocks, ensure_ascii=False)
                ),
                context_snapshot={"project_id": project_id, "operation": "creative_graph", "chapter_id": chapter_id},
            )
            payload = self._parse(result.text, allowed_ordinals=set(range(len(source_blocks))))
            await self._persist(tenant_id, project_id, chapter_id, chapter_title, payload)
            await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED)
        except (AgentRuntimeError, CreativeGraphError, NarrativeGraphError, ValidationError, ValueError) as error:
            await self.runs.transition(
                tenant_id=tenant_id,
                run_id=run.id,
                target=RunStatus.FAILED,
                error_code="creative_graph_extraction_failed",
            )
            raise CreativeGraphError(str(error)) from error

    @staticmethod
    def _parse(text: str, *, allowed_ordinals: set[int]) -> _Payload:
        payload = _Payload.model_validate(CreativeGraphExtractor._payload_object(repair_json(text)))
        cited = {ordinal for node in payload.nodes for ordinal in node.blocks_ordinals}
        cited.update(ordinal for edge in payload.edges for ordinal in edge.blocks_ordinals)
        if not cited <= allowed_ordinals:
            raise CreativeGraphError("graph extraction cited an unknown block ordinal")
        keys = {node.key for node in payload.nodes}
        if any(edge.source not in keys or edge.target not in keys for edge in payload.edges):
            raise CreativeGraphError("graph edge references a node absent from its batch")
        return payload

    @staticmethod
    def _payload_object(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            if {"chapter_title", "chapter_summary", "nodes", "edges"} <= set(value):
                return value
            for nested in value.values():
                try:
                    return CreativeGraphExtractor._payload_object(nested)
                except CreativeGraphError:
                    continue
        if isinstance(value, list):
            for nested in value:
                try:
                    return CreativeGraphExtractor._payload_object(nested)
                except CreativeGraphError:
                    continue
        raise CreativeGraphError("graph extraction did not contain a result object")

    async def _persist(
        self,
        tenant_id: str,
        project_id: str,
        chapter_id: str,
        chapter_title: str,
        payload: _Payload,
    ) -> None:
        """Persist nodes, edges and summary using the existing graph service."""
        # Use a project-scoped index key
        index_key = f"creative:{project_id}"

        async with self.database.session() as session:
            from scriptnow.platform.models import NarrativeIndexModel

            # Ensure an index exists for this creative project
            index = (
                await session.scalars(
                    select(NarrativeIndexModel).where(
                        NarrativeIndexModel.tenant_id == tenant_id,
                        NarrativeIndexModel.id == index_key,
                    )
                )
            ).one_or_none()

            if index is None:
                index = NarrativeIndexModel(
                    id=index_key,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    name="创作图谱",
                    config={"source": "creative", "extraction_status": "ready"},
                )
                session.add(index)
                await session.flush()

        node_ids: list[str] = []
        for node in payload.nodes:
            record = await self.graphs.record_node(
                tenant_id=tenant_id,
                index_id=index_key,
                item=NarrativeNodeInput(
                    node_key=node.key,
                    node_type=node.type.value,
                    name=node.name,
                    aliases=tuple(node.aliases),
                    description=node.description,
                    attributes={},
                    evidence_unit_ids=(),  # No NarrativeTextUnit for creative
                ),
            )
            node_ids.append(record.id)
        for edge in payload.edges:
            await self.graphs.record_edge(
                tenant_id=tenant_id,
                index_id=index_key,
                item=NarrativeEdgeInput(
                    edge_key=edge.key,
                    edge_type=edge.type.value,
                    source_node_key=edge.source,
                    target_node_key=edge.target,
                    description=edge.description,
                    evidence_unit_ids=(),  # No NarrativeTextUnit for creative
                    confidence=edge.confidence,
                    inference=edge.inference,
                ),
            )
        await self.graphs.record_summary(
            tenant_id=tenant_id,
            index_id=index_key,
            item=NarrativeSummaryInput(
                summary_key=f"chapter:{chapter_id}",
                level="chapter",
                title=payload.chapter_title,
                content=payload.chapter_summary,
                child_unit_ids=(),  # No NarrativeTextUnit for creative
                evidence_node_ids=tuple(node_ids),
            ),
        )


# ── Graph reader for Writer context ──────────────────────────────────────


async def read_creative_graph(database: Database, *, project_id: str) -> dict[str, object]:
    """Read the accumulated creative graph as a compact context object.

    Returns a dict with keys: ``chapters`` (list of summaries), ``nodes``,
    ``edges``, suitable for embedding in Writer context.
    """
    index_key = f"creative:{project_id}"

    async with database.session() as session:
        from scriptnow.platform.models import (
            NarrativeEdgeModel,
            NarrativeNodeModel,
            NarrativeSummaryModel,
        )

        summaries = list(
            await session.scalars(
                select(NarrativeSummaryModel)
                .where(NarrativeSummaryModel.index_id == index_key)
                .where(NarrativeSummaryModel.level == "chapter")
                .order_by(NarrativeSummaryModel.created_at)
            )
        )
        nodes = list(
            await session.scalars(
                select(NarrativeNodeModel)
                .where(NarrativeNodeModel.index_id == index_key)
            )
        )
        edges = list(
            await session.scalars(
                select(NarrativeEdgeModel)
                .where(NarrativeEdgeModel.index_id == index_key)
            )
        )

    return {
        "chapters": [
            {
                "chapter_key": s.summary_key,
                "title": s.title,
                "summary": s.content,
            }
            for s in summaries
        ],
        "nodes": [
            {
                "key": n.node_key,
                "type": n.node_type,
                "name": n.name,
                "aliases": list(n.aliases),
                "description": n.description,
            }
            for n in nodes
        ],
        "edges": [
            {
                "key": e.edge_key,
                "type": e.edge_type,
                "source": e.source_node_key,
                "target": e.target_node_key,
                "description": e.description,
                "confidence": e.confidence,
                "inference": e.inference,
            }
            for e in edges
        ],
    }
