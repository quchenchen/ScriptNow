import json
import logging
import re
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select

from scriptflow_v7.novel.domain import NovelStoryCoreDraft
from scriptflow_v7.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
from scriptflow_v7.platform.billing import BillingService
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    ProjectEventModel,
    ProjectModel,
    RagChunkModel,
    RunStatus,
    TenantModel,
)
from scriptflow_v7.platform.run_coordinator import RunCoordinator
from scriptflow_v7.platform.run_events import RunEventType

logger = logging.getLogger(__name__)


class NovelIdeationError(RuntimeError):
    pass


class _RetrievalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: tuple[str, ...] = Field(min_length=3, max_length=32)
    coverage_gaps: tuple[str, ...] = Field(default=(), max_length=32)
    sufficient: bool = False


@dataclass(frozen=True, slots=True)
class _SourceChunk:
    ordinal: int
    content: str


class _Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=160)
    premise: str = Field(min_length=80)
    point_of_view: str = Field(min_length=2, max_length=500)
    narrative_constraints: tuple[str, ...] = Field(min_length=2, max_length=8)
    angles: tuple[str, ...] = Field(min_length=5, max_length=5)


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: tuple[_Candidate, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def distinct_candidates(self) -> "_Payload":
        titles = {item.title.casefold().strip() for item in self.candidates}
        premises = {item.premise.casefold().strip() for item in self.candidates}
        if len(titles) != 3 or len(premises) != 3:
            raise ValueError("three genuinely distinct candidates are required")
        return self


class NovelIdeationGenerator:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        runtime: AgentRuntime | None = None,
    ) -> None:
        self.database = database
        self.runtime = runtime or AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.environment == "production"
        )

    async def generate(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        feedback: str | None,
    ) -> tuple[NovelStoryCoreDraft, ...]:
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project.id)
        director = dict(dict(status["roles"])["director"])
        if not director.get("connected"):
            raise NovelIdeationError(
                f"real director runtime is unavailable: {director.get('reason') or 'unknown'}"
            )
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"novel-ideation:{idempotency_key}",
        )
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            if tenant is None:
                raise NovelIdeationError("tenant does not exist")
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"novel-ideation:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=24_000,
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        try:
            await self._project_event(
                tenant_id=tenant_id,
                project_id=project.id,
                run_id=run.id,
                step="request",
                type=RunEventType.CONVERSATION,
                title="作家请求重新发散",
                content=feedback or "请重新比较三个小说创意方向。",
            )
            source, retrieval_plans = await self._retrieval_loop(
                tenant_id=tenant_id,
                project=project,
                feedback=feedback,
                run_id=run.id,
            )
            await self._project_event(
                tenant_id=tenant_id,
                project_id=project.id,
                run_id=run.id,
                step="compare",
                type=RunEventType.NODE,
                title="正在比较三个故事方向",
                content="灵感导演正在依据原稿证据比较不同的改编策略。",
            )
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
                role="director",
                content=self._prompt(project, feedback),
                context_snapshot={
                    "project_id": project.id,
                    "source_mode": project.source_mode,
                    "source_excerpts": source,
                    "rag_iterations": len(retrieval_plans),
                    "rag_queries": [query for plan in retrieval_plans for query in plan.queries],
                    "rag_coverage_gaps": [
                        gap for plan in retrieval_plans for gap in plan.coverage_gaps
                    ],
                },
            )
            payload = self.parse(result.text)
            await self._project_event(
                tenant_id=tenant_id,
                project_id=project.id,
                run_id=run.id,
                step="complete",
                type=RunEventType.CONVERSATION,
                title="三个新方向已生成",
                content="\n".join(f"- {item.title}" for item in payload.candidates),
            )
            await self._record_usage(
                reservation_id=reservation.id,
                tenant_id=tenant_id,
                run_id=run.id,
                event_id=f"novel-ideation:{run.id}",
                result=result,
            )
            await self.billing.finalize(reservation.id)
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            return tuple(
                NovelStoryCoreDraft(
                    title=item.title,
                    premise=item.premise,
                    point_of_view=item.point_of_view,
                    narrative_constraints=item.narrative_constraints,
                    angles=item.angles,
                )
                for item in payload.candidates
            )
        except Exception as error:
            logger.exception(
                "novel ideation failed",
                extra={"run_id": run.id, "project_id": project.id},
            )
            with suppress(Exception):
                await self._project_event(
                    tenant_id=tenant_id,
                    project_id=project.id,
                    run_id=run.id,
                    step="failed",
                    type=RunEventType.SYSTEM,
                    title="创意发散暂未完成",
                    content="本轮没有替换旧候选，可以保留修订要求后再次尝试。",
                    status="failed",
                )
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="novel_ideation_failed",
                )
            if isinstance(error, NovelIdeationError):
                raise
            if isinstance(error, AgentRuntimeError):
                raise NovelIdeationError(str(error)) from error
            raise NovelIdeationError(f"invalid director output: {error}") from error

    async def _all_source_chunks(
        self, *, tenant_id: str, project_id: str
    ) -> list[_SourceChunk]:
        async with self.database.session() as session:
            chunks = list(
                await session.scalars(
                    select(RagChunkModel)
                    .where(
                        RagChunkModel.tenant_id == tenant_id,
                        RagChunkModel.project_id == project_id,
                    )
                    .order_by(RagChunkModel.ordinal)
                )
            )
        return [_SourceChunk(item.ordinal, item.content[:2_000]) for item in chunks]

    async def _retrieval_loop(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        feedback: str | None,
        run_id: str,
    ) -> tuple[list[dict[str, object]], list[_RetrievalPlan]]:
        chunks = await self._all_source_chunks(tenant_id=tenant_id, project_id=project.id)
        if not chunks:
            return [], []
        seed_indexes = sorted(
            {round(index * (len(chunks) - 1) / 9) for index in range(min(10, len(chunks)))}
        )
        selected: dict[int, _SourceChunk] = {chunks[index].ordinal: chunks[index] for index in seed_indexes}
        first_plan = self._initial_retrieval_plan(project, feedback)
        for chunk in self._rank_chunks(chunks, first_plan.queries, limit=18):
            selected.setdefault(chunk.ordinal, chunk)
        await self._project_event(
            tenant_id=tenant_id,
            project_id=project.id,
            run_id=run_id,
            step="retrieve-1",
            type=RunEventType.NODE,
            title="正在查阅素材（第 1/2 轮）",
            content="已定位人物、核心冲突与改编边界。",
        )
        # The second pass is derived from evidence added by the first pass.
        second_plan = self._expansion_retrieval_plan(selected)
        for chunk in self._rank_chunks(chunks, second_plan.queries, limit=18):
            selected.setdefault(chunk.ordinal, chunk)
        await self._project_event(
            tenant_id=tenant_id,
            project_id=project.id,
            run_id=run_id,
            step="retrieve-2",
            type=RunEventType.NODE,
            title="正在查阅素材（第 2/2 轮）",
            content="已补充人物关系、关键证据、结局与伏笔信息。",
        )
        iterations = [first_plan, second_plan]
        return self._source_payload(selected.values(), max_chars=46_000), iterations

    async def _project_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        step: str,
        type: RunEventType,
        title: str,
        content: str,
        status: str | None = None,
    ) -> None:
        event_key = f"novel:ideation:{run_id}:{step}"
        stream_key = f"project:{project_id}"
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(ProjectEventModel).where(
                        ProjectEventModel.stream_key == stream_key,
                        ProjectEventModel.event_key == event_key,
                    )
                )
            ).one_or_none()
            if existing:
                return
            sequence = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(ProjectEventModel.sequence), 0)).where(
                            ProjectEventModel.stream_key == stream_key
                        )
                    )
                    or 0
                )
                + 1
            )
            payload: dict[str, object] = {
                "title": title,
                "content": content,
                "role": "director",
                "schema_version": 1,
            }
            if status:
                payload["status"] = status
            session.add(
                ProjectEventModel(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    stream_key=stream_key,
                    sequence=sequence,
                    event_key=event_key,
                    event_type=type,
                    schema_version=1,
                    actor={"type": "agent", "role": "director"},
                    aggregate={"type": "novel_ideation", "id": project_id},
                    causation_id=None,
                    correlation_id=run_id,
                    idempotency_key=event_key,
                    payload=payload,
                )
            )

    @staticmethod
    def _initial_retrieval_plan(
        project: ProjectModel, feedback: str | None
    ) -> _RetrievalPlan:
        direction = dict(project.direction)
        anchors = " ".join(
            str(direction.get(key) or "")
            for key in ("genre", "premise", "core_idea", "tone", "must_keep")
        )
        feedback_text = feedback or ""
        terms = NovelIdeationGenerator._search_terms(f"{anchors} {feedback_text}")
        project_queries = [" ".join(terms[index : index + 4]) for index in range(0, len(terms), 4)]
        queries = tuple(
            dict.fromkeys(
                [
                    "protagonist identity desire need",
                    "bond rejection protection relationship betrayal",
                    "wolf law bloodline constitutional power antagonist",
                    "midpoint reversal climax ending sacrifice",
                    *[query for query in project_queries if query],
                ]
            )
        )
        return _RetrievalPlan(
            queries=queries[:32],
            coverage_gaps=("named relationships", "ending cost", "source fidelity risks"),
            sufficient=False,
        )

    @staticmethod
    def _expansion_retrieval_plan(selected: dict[int, _SourceChunk]) -> _RetrievalPlan:
        evidence = "\n".join(item.content for item in selected.values())
        names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", evidence)
        frequent_names = sorted(
            set(names), key=lambda value: (-evidence.count(value), value)
        )[:10]
        queries = tuple(
            dict.fromkeys(
                [
                    *[f"{name} secret motive relationship" for name in frequent_names],
                    "Silver Vael Cassius massacre evidence",
                    "Kael rejection protection council legitimacy",
                    "final battle binding judgment ending",
                    "hairpin forty-three coins payoff",
                ]
            )
        )
        return _RetrievalPlan(
            queries=queries[:32],
            coverage_gaps=(),
            sufficient=True,
        )

    @staticmethod
    def _search_terms(text: str) -> list[str]:
        ignored = {"the", "and", "with", "from", "this", "that", "into", "three", "different"}
        return list(
            dict.fromkeys(
                token.casefold()
                for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}|[\u4e00-\u9fff]{2,}", text)
                if token.casefold() not in ignored
            )
        )[:40]

    @staticmethod
    def _source_payload(
        chunks: Iterable[_SourceChunk], *, max_chars: int
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        used = 0
        for item in sorted(chunks, key=lambda value: value.ordinal):
            content = item.content[:2_000]
            if used + len(content) > max_chars:
                break
            result.append({"ordinal": item.ordinal, "content": content})
            used += len(content)
        return result

    @staticmethod
    def _rank_chunks(
        chunks: list[_SourceChunk], queries: tuple[str, ...], *, limit: int
    ) -> list[_SourceChunk]:
        terms = {
            token.casefold()
            for query in queries
            for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}|[\u4e00-\u9fff]{2,}", query)
        }
        scored = []
        for chunk in chunks:
            text = chunk.content.casefold()
            score = sum(text.count(term) for term in terms)
            if score:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].ordinal))
        return [item for _, item in scored[:limit]]

    @staticmethod
    def _retrieval_prompt(
        project: ProjectModel,
        feedback: str | None,
        iteration: int,
        previous_gaps: tuple[str, ...],
    ) -> str:
        return (
            "Use the adaptation source excerpts as evidence. Plan the next retrieval pass before "
            "ideation. Produce search queries that cover named protagonists, relationship history, "
            "wolf mythology and rules, factions and antagonists, major reversals, emotional promises, "
            "and ending material. Do not propose a story direction yet.\n"
            f"Iteration: {iteration}. Previous coverage gaps: {list(previous_gaps)}.\n"
            f"Project direction: {json.dumps(project.direction, ensure_ascii=False)}\n"
            f"User feedback: {feedback or 'none'}\n"
            "Return JSON only: "
            '{"queries":["three or more source-grounded search phrases"],'
            '"coverage_gaps":["remaining evidence gaps"],"sufficient":false}'
        )

    async def _record_usage(
        self,
        *,
        reservation_id: str,
        tenant_id: str,
        run_id: str,
        event_id: str,
        result: AgentRuntimeResult,
    ) -> None:
        await self.billing.record_model_call(
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            run_id=run_id,
            framework_event_id=event_id,
            trace_id=run_id,
            agent_role="director",
            model_key=result.model_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_price_per_million=result.input_price_per_million,
            output_price_per_million=result.output_price_per_million,
        )

    @staticmethod
    def _prompt(project: ProjectModel, feedback: str | None) -> str:
        language = str(project.direction.get("language") or "zh-CN")
        return (
            "Use the novel-ideate skill and the supplied adaptation excerpts to create exactly "
            "three genuinely different novel directions. Preserve source character relationships "
            "and emotional promises where they are supported by excerpts; do not claim facts that "
            "are absent. Each direction must differ in dramatic engine, central dilemma, escalation, "
            "relationship trajectory, and ending cost.\n"
            f"Required creative language: {language}. Every string in the result must use that language.\n"
            f"Project direction: {json.dumps(project.direction, ensure_ascii=False)}\n"
            f"Revision feedback: {feedback or 'none'}\n"
            "Return JSON only, with no markdown fence, using this exact schema:\n"
            '{"candidates":[{"title":"...","premise":"80+ characters describing protagonist desire, '
            'opposition, escalation, emotional promise, moral dilemma and ending direction",'
            '"point_of_view":"...","narrative_constraints":["...","..."],'
            '"angles":["protagonist desire: ...","opposing force: ...","emotional promise: ...",'
            '"moral dilemma: ...","ending cost: ..."]}]}'
        )

    @staticmethod
    def parse(text: str) -> _Payload:
        value = NovelIdeationGenerator._json_document(text)
        try:
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                raw = repair_json(value, schema=_Payload.model_json_schema())
            if isinstance(raw, list):
                raw = {"candidates": raw}
            return _Payload.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as error:
            raise NovelIdeationError(str(error)) from error

    @staticmethod
    def parse_retrieval_plan(text: str) -> _RetrievalPlan:
        value = NovelIdeationGenerator._json_document(text)
        try:
            raw = json.loads(value)
            if isinstance(raw, dict):
                if isinstance(raw.get("queries"), list):
                    raw["queries"] = raw["queries"][:32]
                if isinstance(raw.get("coverage_gaps"), list):
                    raw["coverage_gaps"] = raw["coverage_gaps"][:32]
            return _RetrievalPlan.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as error:
            raise NovelIdeationError(f"invalid RAG plan: {error}") from error

    @staticmethod
    def _json_document(text: str) -> str:
        value = text.strip()
        fenced = re.findall(
            r"```(?:json)?\s*(.*?)\s*```",
            value,
            re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            return fenced[-1].strip()
        return value
