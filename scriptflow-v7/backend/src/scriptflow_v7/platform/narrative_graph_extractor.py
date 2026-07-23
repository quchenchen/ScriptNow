import json
from collections import OrderedDict

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from scriptflow_v7.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    NarrativeIndexModel,
    NarrativeSummaryModel,
    NarrativeTextUnitModel,
    ProjectModel,
    RunStatus,
)
from scriptflow_v7.platform.narrative_graph import (
    NarrativeEdgeInput,
    NarrativeGraphError,
    NarrativeGraphService,
    NarrativeNodeInput,
    NarrativeSummaryInput,
)
from scriptflow_v7.platform.narrative_graph_schema import (
    NODE_TYPE_VALUES,
    RELATION_TYPE_VALUES,
    NarrativeNodeType,
    NarrativeRelationType,
    canonical_node_type,
    canonical_relation_type,
)
from scriptflow_v7.platform.run_coordinator import RunCoordinator


class NarrativeGraphExtractionError(RuntimeError):
    pass


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=3, max_length=160)
    type: NarrativeNodeType
    name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=12)
    description: str = Field(min_length=1, max_length=1200)
    evidence_ordinals: list[int] = Field(min_length=1, max_length=20)

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
    evidence_ordinals: list[int] = Field(min_length=1, max_length=20)
    confidence: int = Field(ge=0, le=100)
    inference: bool = False

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> NarrativeRelationType:
        if not isinstance(value, str):
            raise ValueError("narrative relation type must be a string")
        return canonical_relation_type(value)


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_title: str = Field(min_length=1, max_length=300)
    chapter_summary: str = Field(min_length=1, max_length=1800)
    nodes: list[_Node] = Field(default_factory=list, max_length=40)
    edges: list[_Edge] = Field(default_factory=list, max_length=80)


class NarrativeGraphExtractor:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.graphs = NarrativeGraphService(database)

    async def extract(self, *, tenant_id: str, project_id: str, index_id: str) -> None:
        async with self.database.session() as session:
            index = await session.get(NarrativeIndexModel, index_id)
            project = await session.get(ProjectModel, project_id)
            if index is None or index.tenant_id != tenant_id or index.project_id != project_id or project is None:
                raise NarrativeGraphExtractionError("narrative index is outside project scope")
            units = list(
                await session.scalars(
                    select(NarrativeTextUnitModel)
                    .where(NarrativeTextUnitModel.index_id == index_id)
                    .order_by(NarrativeTextUnitModel.ordinal)
                )
            )
            completed_summary_keys = set(
                await session.scalars(
                    select(NarrativeSummaryModel.summary_key).where(
                        NarrativeSummaryModel.index_id == index_id,
                        NarrativeSummaryModel.level == "chapter",
                    )
                )
            )
            index.config = {
                **dict(index.config),
                "extraction_status": "running",
                "extraction_error": None,
                "extraction_completed": len(completed_summary_keys),
                "extraction_attempt": int(dict(index.config).get("extraction_attempt", 0)) + 1,
            }
            attempt = int(index.config["extraction_attempt"])
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        architect = dict(dict(status["roles"])["architect"])
        if not architect.get("connected"):
            await self._mark(index_id, "failed", str(architect.get("reason") or "runtime unavailable"))
            raise NarrativeGraphExtractionError("story graph runtime is unavailable")
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=f"narrative-graph:{index_id}:v2:{attempt}",
        )
        if run.status == RunStatus.QUEUED:
            await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        chapters: OrderedDict[str, list[NarrativeTextUnitModel]] = OrderedDict()
        for unit in units:
            chapters.setdefault(unit.chapter_key, []).append(unit)
        completed_count = len(completed_summary_keys)
        await self._progress(index_id, completed=completed_count, total=len(chapters))
        try:
            for chapter_key, chapter_units in chapters.items():
                if f"chapter:{chapter_key}" in completed_summary_keys:
                    continue
                payload = await self._extract_chapter(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    project=project,
                    units=chapter_units,
                )
                await self._persist(tenant_id, index_id, chapter_key, chapter_units, payload)
                completed_count += 1
                await self._progress(index_id, completed=completed_count, total=len(chapters))
            await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED)
            await self._mark(index_id, "ready", None)
        except (AgentRuntimeError, NarrativeGraphError, NarrativeGraphExtractionError, ValidationError, ValueError) as error:
            await self.runs.transition(
                tenant_id=tenant_id,
                run_id=run.id,
                target=RunStatus.FAILED,
                error_code="narrative_graph_extraction_failed",
            )
            await self._mark(index_id, "failed", str(error)[:500])
            raise NarrativeGraphExtractionError(str(error)) from error

    async def _extract_chapter(self, *, tenant_id: str, run_id: str, project: ProjectModel, units: list[NarrativeTextUnitModel]) -> _Payload:
        source = [
            {"ordinal": unit.ordinal, "chapter": unit.chapter_title, "text": unit.content}
            for unit in units
        ]
        result = await self.runtime.generate(
            tenant_id=tenant_id,
            run_id=run_id,
            role="architect",
            stage_override="source-analysis",
            explicit_skill_keys=("novel-build-story-graph",),
            content=(
                "Extract an evidence-grounded narrative graph for this chapter batch. Return JSON only: "
                '{"chapter_title":"...","chapter_summary":"what changes and remains unresolved",'
                f'"nodes":[{{"key":"type:stable-key","type":"{"|".join(NODE_TYPE_VALUES)}",'
                '"name":"...","aliases":[],"description":"...","evidence_ordinals":[0]}],'
                f'"edges":[{{"key":"...","type":"{"|".join(RELATION_TYPE_VALUES)}","source":"node-key","target":"node-key",'
                '"description":"...","evidence_ordinals":[0],"confidence":90,"inference":false}]}.'
                " Every ordinal must exist in the supplied batch. Do not quote long prose.\n"
                + json.dumps(source, ensure_ascii=False)
            ),
            context_snapshot={"project_id": project.id, "operation": "narrative_graph", "unit_ordinals": [unit.ordinal for unit in units]},
        )
        return self.parse(result.text, allowed_ordinals={unit.ordinal for unit in units})

    @staticmethod
    def parse(text: str, *, allowed_ordinals: set[int]) -> _Payload:
        payload = _Payload.model_validate(NarrativeGraphExtractor._payload_object(repair_json(text)))
        cited = {ordinal for node in payload.nodes for ordinal in node.evidence_ordinals}
        cited.update(ordinal for edge in payload.edges for ordinal in edge.evidence_ordinals)
        if not cited <= allowed_ordinals:
            raise NarrativeGraphExtractionError("graph extraction cited an unknown source unit")
        keys = {node.key for node in payload.nodes}
        if any(edge.source not in keys or edge.target not in keys for edge in payload.edges):
            raise NarrativeGraphExtractionError("graph edge references a node absent from its batch")
        return payload

    @staticmethod
    def _payload_object(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            if {"chapter_title", "chapter_summary", "nodes", "edges"} <= set(value):
                return value
            for nested in value.values():
                try:
                    return NarrativeGraphExtractor._payload_object(nested)
                except NarrativeGraphExtractionError:
                    continue
        if isinstance(value, list):
            for nested in value:
                try:
                    return NarrativeGraphExtractor._payload_object(nested)
                except NarrativeGraphExtractionError:
                    continue
        raise NarrativeGraphExtractionError("graph extraction did not contain a result object")

    async def _persist(self, tenant_id: str, index_id: str, chapter_key: str, units: list[NarrativeTextUnitModel], payload: _Payload) -> None:
        by_ordinal = {unit.ordinal: unit.id for unit in units}
        node_ids: list[str] = []
        for node in payload.nodes:
            record = await self.graphs.record_node(
                tenant_id=tenant_id,
                index_id=index_id,
                item=NarrativeNodeInput(node_key=node.key, node_type=node.type.value, name=node.name, aliases=tuple(node.aliases), description=node.description, attributes={}, evidence_unit_ids=tuple(by_ordinal[item] for item in node.evidence_ordinals)),
            )
            node_ids.append(record.id)
        for edge in payload.edges:
            await self.graphs.record_edge(
                tenant_id=tenant_id,
                index_id=index_id,
                item=NarrativeEdgeInput(edge_key=edge.key, edge_type=edge.type.value, source_node_key=edge.source, target_node_key=edge.target, description=edge.description, evidence_unit_ids=tuple(by_ordinal[item] for item in edge.evidence_ordinals), confidence=edge.confidence, inference=edge.inference),
            )
        await self.graphs.record_summary(
            tenant_id=tenant_id,
            index_id=index_id,
            item=NarrativeSummaryInput(summary_key=f"chapter:{chapter_key}", level="chapter", title=payload.chapter_title, content=payload.chapter_summary, child_unit_ids=tuple(unit.id for unit in units), evidence_node_ids=tuple(node_ids)),
        )

    async def _mark(self, index_id: str, extraction_status: str, error: str | None) -> None:
        async with self.database.session() as session:
            index = await session.get(NarrativeIndexModel, index_id)
            if index is not None:
                index.config = {**dict(index.config), "extraction_status": extraction_status, "extraction_error": error}

    async def _progress(self, index_id: str, *, completed: int, total: int) -> None:
        async with self.database.session() as session:
            index = await session.get(NarrativeIndexModel, index_id)
            if index is not None:
                index.config = {
                    **dict(index.config),
                    "extraction_completed": completed,
                    "extraction_total": total,
                }
