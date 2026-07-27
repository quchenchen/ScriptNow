import asyncio
import json
import logging
import re
from contextlib import suppress

from agentscope.event import (
    AgentEvent,
    CustomEvent,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from scriptnow.novel.continuity import latest_effective_revisions
from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.domain import (
    NovelBlueprintModel,
    NovelCandidateStatus,
    NovelDocumentRevisionModel,
    NovelStoryCoreCandidateModel,
)
from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.novel.writer_context import (
    build_character_graph,
    build_narrative_state,
    build_prior_summary,
    build_review_highlights,
)
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType

logger = logging.getLogger(__name__)


class NovelWriterError(RuntimeError):
    pass


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern=r"^(heading|prose|dialogue|quote|divider)$")
    text: str

    @model_validator(mode="after")
    def validate_text_contract(self) -> "_Block":
        if self.type != "divider" and not self.text.strip():
            raise ValueError("readable novel blocks require text")
        return self


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    blocks: tuple[_Block, ...] = Field(min_length=3, max_length=240)

    @model_validator(mode="after")
    def ensure_prose(self) -> "_Payload":
        if self.blocks[0].type != "heading":
            raise ValueError("the first novel block must be a heading")
        if not any(item.type in {"prose", "dialogue", "quote"} for item in self.blocks[1:]):
            raise ValueError("the chapter must contain readable narrative blocks")
        return self


class NovelChapterGenerator:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.events = PersistentRunEventLog(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
        )

    async def generate(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        chapter_id: str,
        idempotency_key: str,
        feedback: str | None = None,
        source_revision_id: str | None = None,
    ) -> tuple[NovelBlock, ...]:
        context = await self._context(
            tenant_id=tenant_id,
            project=project,
            chapter_id=chapter_id,
            source_revision_id=source_revision_id,
        )
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project.id)
        writer = dict(dict(status["roles"])["writer"])
        if self.settings.environment != "production" and writer.get("reason") == "mock_only":
            return self._test_blocks(context)
        if not writer.get("connected"):
            raise NovelWriterError(
                f"real writer runtime is unavailable: {writer.get('reason') or 'unknown'}"
            )
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"novel-chapter:{chapter_id}:{idempotency_key}",
        )
        tenant = context.pop("tenant")
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"novel-chapter:{chapter_id}:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=min(
                self.settings.novel_writer_max_reserved_tokens,
                max(
                    self.settings.novel_writer_min_reserved_tokens,
                    int(
                        int(context["chapter"]["target_words"])
                        * self.settings.novel_writer_token_reserve_ratio
                    ),
                ),
            ),
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        await self._event(
            tenant_id=tenant_id,
            run_id=run.id,
            key="context-ready",
            type=RunEventType.NODE,
            payload={
                "block": "data",
                "phase": "end",
                "title": "第一章创作上下文已装配" if chapter_id == "chapter-1" else "章节创作上下文已装配",
                "data": {
                    "phase": "章节写作",
                    "story_units": 1,
                    "adopted_units": len(list(context.get("prior_chapter_revisions") or [])),
                    "open_findings": 0,
                },
                "runtime": "agentscope",
            },
        )
        await self._event(
            tenant_id=tenant_id,
            run_id=run.id,
            key="writer-started",
            type=RunEventType.SYSTEM,
            payload={
                "block": "system",
                "phase": "start",
                "title": "主笔正在生成章节候选稿",
                "runtime": "agentscope",
            },
        )
        heartbeat = asyncio.create_task(
            self._heartbeat(tenant_id=tenant_id, run_id=run.id, chapter_id=chapter_id)
        )
        stream_sequence = 0

        tool_names: dict[str, str] = {}

        async def stream_candidate(event: AgentEvent) -> None:
            nonlocal stream_sequence
            stream_sequence += 1
            if isinstance(event, ThinkingBlockDeltaEvent):
                payload = {
                    "block": "thinking",
                    "phase": "delta",
                    "delta": event.delta,
                    "title": "主笔的创作思路",
                    "chapter_id": chapter_id,
                    "runtime": "agentscope",
                }
                event_type = RunEventType.CONVERSATION
            elif isinstance(event, ToolCallStartEvent):
                tool_names[event.tool_call_id] = event.tool_call_name
                payload = {
                    "block": "tool",
                    "phase": "skills",
                    "title": f"正在调用 {event.tool_call_name}",
                    "tool_call_id": event.tool_call_id,
                    "chapter_id": chapter_id,
                    "runtime": "agentscope",
                }
                event_type = RunEventType.NODE
            elif isinstance(event, ToolCallEndEvent | ToolResultEndEvent):
                tool_name = tool_names.get(event.tool_call_id, "创作能力")
                payload = {
                    "block": "tool",
                    "phase": "skills",
                    "title": f"{tool_name} 调用完成",
                    "tool_call_id": event.tool_call_id,
                    "state": str(event.state) if isinstance(event, ToolResultEndEvent) else None,
                    "chapter_id": chapter_id,
                    "runtime": "agentscope",
                }
                event_type = RunEventType.NODE
            elif isinstance(event, CustomEvent) and event.name in {
                "scriptnow.phase",
                "scriptflow.phase",
            }:
                payload = {
                    "block": "system",
                    "phase": str(event.value.get("phase") or "planning"),
                    "title": str(event.value.get("title") or "创作阶段更新"),
                    "chapter_id": chapter_id,
                    "runtime": "agentscope",
                }
                event_type = RunEventType.SYSTEM
            elif isinstance(event, TextBlockDeltaEvent):
                payload = {
                    "block": "text",
                    "phase": "delta",
                    "delta": event.delta,
                    "title": "章节候选稿只读预览",
                    "chapter_id": chapter_id,
                    "preview": True,
                    "runtime": "agentscope",
                }
                event_type = RunEventType.CONVERSATION
            else:
                return
            await self._event(
                tenant_id=tenant_id,
                run_id=run.id,
                key=f"runtime-phase-{stream_sequence}",
                type=event_type,
                payload=payload,
            )
        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
                role="writer",
                content=self._prompt(project, context, feedback),
                context_snapshot=context,
                event_sink=stream_candidate,
            )
            blocks = self.parse(result.text, run.id)
            target_words = int(dict(context["chapter"])["target_words"])
            maximum_words = round(target_words * 1.2)
            actual_words = self.count_manuscript_units(
                blocks,
                str(context["creative_language"]),
            )
            if actual_words > maximum_words:
                unit = (
                    "words"
                    if str(context["creative_language"]).lower().startswith("en")
                    else "字"
                )
                await self._event(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    key="writer-length-warning",
                    type=RunEventType.SYSTEM,
                    payload={
                        "block": "system",
                        "phase": "warning",
                        "title": (
                            f"候选稿为 {actual_words} {unit}，超出建议区间上限 "
                            f"{maximum_words} {unit}；可保留内容后人工压缩"
                        ),
                        "chapter_id": chapter_id,
                        "actual_units": actual_words,
                        "target_units": target_words,
                        "maximum_units": maximum_words,
                        "runtime": result.runtime,
                    },
                )
            await self._record_usage(reservation.id, tenant_id, run.id, result)
            await self.billing.finalize(reservation.id)
            await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED)
            await self._event(
                tenant_id=tenant_id,
                run_id=run.id,
                key="writer-completed",
                type=RunEventType.TERMINAL,
                payload={
                    "block": "system",
                    "phase": "end",
                    "title": "章节候选稿已生成并通过结构校验",
                    "runtime": result.runtime,
                },
            )
            return blocks
        except asyncio.CancelledError:
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.CANCELLED,
                )
            with suppress(Exception):
                await self._event(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    key="writer-cancelled",
                    type=RunEventType.TERMINAL,
                    payload={
                        "block": "system",
                        "phase": "end",
                        "title": "章节候选稿生成已取消",
                        "runtime": "agentscope",
                    },
                )
            raise
        except Exception as error:
            logger.exception("novel chapter generation failed", extra={"run_id": run.id, "chapter_id": chapter_id})
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="novel_chapter_failed",
                )
            with suppress(Exception):
                await self._event(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    key="writer-failed",
                    type=RunEventType.TERMINAL,
                    payload={
                        "block": "system",
                        "phase": "end",
                        "title": "章节候选稿生成未完成",
                        "runtime": "agentscope",
                    },
                )
            if isinstance(error, NovelWriterError | AgentRuntimeError):
                raise NovelWriterError(str(error)) from error
            raise NovelWriterError(f"invalid writer output: {error}") from error
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat(self, *, tenant_id: str, run_id: str, chapter_id: str) -> None:
        elapsed = 0
        while True:
            await asyncio.sleep(30)
            elapsed += 30
            await self._event(
                tenant_id=tenant_id,
                run_id=run_id,
                # A heartbeat refreshes one operational status. Giving every tick a
                # new identity floods the Dock with semantically identical cards.
                key="writer-heartbeat",
                type=RunEventType.HEARTBEAT,
                payload={
                    "block": "system",
                    "phase": "delta",
                    "title": "主笔仍在创作，候选稿将在校验完成后解锁",
                    "chapter_id": chapter_id,
                    "elapsed_seconds": elapsed,
                    "runtime": "agentscope",
                },
            )

    async def _event(
        self,
        *,
        tenant_id: str,
        run_id: str,
        key: str,
        type: RunEventType,
        payload: dict[str, object],
    ) -> None:
        await self.events.append(
            tenant_id=tenant_id,
            run_id=run_id,
            event_key=f"novel-writer:{key}",
            type=type,
            payload=payload,
            correlation_id=run_id,
        )

    async def _context(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        chapter_id: str,
        source_revision_id: str | None = None,
    ) -> dict[str, object]:
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project.id)
                )
            ).one_or_none()
            core = (
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project.id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            blueprint = (
                await session.scalars(
                    select(NovelBlueprintModel).where(
                        NovelBlueprintModel.project_id == project.id,
                        NovelBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            revisions = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel)
                    .where(NovelDocumentRevisionModel.project_id == project.id)
                )
            )
        if tenant is None or story_map is None or core is None or blueprint is None:
            raise NovelWriterError("adopted direction, blueprint and StoryMap are required")
        chapter = next(
            (
                dict(item)
                for volume in story_map.volumes
                for item in list(dict(volume).get("chapters") or [])
                if str(dict(item).get("id")) == chapter_id
            ),
            None,
        )
        if chapter is None:
            raise NovelWriterError("chapter does not exist in the adopted StoryMap")
        chapter_ids = [
            str(dict(item).get("id"))
            for volume in story_map.volumes
            for item in list(dict(volume).get("chapters") or [])
        ]
        prior = latest_effective_revisions(
            revisions,
            chapter_ids=chapter_ids,
            before_chapter_id=chapter_id,
        )
        source_revision = next(
            (
                item
                for item in revisions
                if item.id == source_revision_id and item.chapter_id == chapter_id
            ),
            None,
        )
        if source_revision_id and source_revision is None:
            raise NovelWriterError("需要调整的候选版本不存在，当前版本未受影响。")
        return {
            "tenant": tenant,
            "project_id": project.id,
            "project_name": project.name,
            "creative_language": str(project.direction.get("language") or ""),
            "direction": {
                "title": core.title,
                "premise": core.premise,
                "point_of_view": core.point_of_view,
                "constraints": list(core.narrative_constraints),
            },
            "chapter": chapter,
            "prior_chapters_summary": build_prior_summary(prior, chapter_id),
            "character_graph": await build_character_graph(
                self.database, project.id, chapter_id
            ),
            "narrative_state": await build_narrative_state(
                project.id, prior
            ),
            "review_highlights": await build_review_highlights(
                self.database, project.id, chapter_id
            ),
            "source_revision": (
                {
                    "revision_id": source_revision.id,
                    "revision_number": source_revision.revision_number,
                    "source": source_revision.source,
                    "status": source_revision.status,
                    "blocks": list(source_revision.blocks),
                }
                if source_revision
                else None
            ),
        }

    @staticmethod
    def _prompt(project: ProjectModel, context: dict[str, object], feedback: str | None) -> str:
        chapter = dict(context["chapter"])
        source_instruction = (
            "A source revision is included in the writing context. Treat this as a bounded revision task: "
            "preserve its established events, causality, character choices, voice, strongest images, climax "
            "and ending. Apply the feedback by editing that manuscript; do not restart from the premise, "
            "introduce a different plot, or add new scenes merely to improve the prose. When the feedback asks "
            "for compression, delete repeated explanation, merge transitions, shorten description and dialogue, "
            "and verify the requested word budget before returning the final JSON. "
            if context.get("source_revision")
            else ""
        )
        return (
            "Write the requested NOVEL chapter as a candidate revision. Follow every adopted StoryMap beat "
            "for this chapter in order, "
            "point of view, character motives, relationship state, world rules, setup/payoff obligations and "
            "continuity from prior chapter revisions. For each preceding chapter, the context contains the "
            "latest validated revision (including human revisions), which overrides older adopted prose. "
            "Do not write screenplay sluglines or production notes. "
            "Do not explain your process. Use scene-level action, sensory detail, interiority and dialogue. "
            "\nHOT CONTEXT (always visible):\n"
            f"- Direction: {json.dumps(context.get('direction', {}), ensure_ascii=False)[:500]}\n"
            f"- This chapter: {json.dumps(context.get('chapter', {}), ensure_ascii=False)[:300]}\n"
            "\nWARM CONTEXT (pre-computed, read carefully):\n"
            f"{context.get('prior_chapters_summary', '')[:3000]}\n"
            f"{context.get('review_highlights', '')[:1000]}\n"
            f"{context.get('narrative_state', '')[:2000]}\n"
            "\nCOLD CONTEXT (reference only):\n"
            f"{context.get('character_graph', '')[:1000]}\n"
            "\nAfter reviewing the context above, write the chapter following your loaded skills "
            "(novel-write, novel-continuity-check, novel-pacing-check, novel-emotional-depth). "
            "Return JSON only with the blocks schema.\n"
            f"{source_instruction}"
            f"The creative language is {context['creative_language']}; every narrative string must use it. "
            f"The chapter limit is {chapter['target_words']} words. Count whitespace-delimited words "
            "for English and Han characters for Chinese. For limits at or below 1500, draft at 70% to 82% of "
            "the limit and reserve the remaining budget for provider tokenization differences. For longer work, "
            "target 85% to 92%. The hard cap is absolute: compress setup, transitions, description, and repeated "
            "emotional explanation before sacrificing the climax, choice, or consequence. The validator accepts "
            "a final variance of up to 20%, but do not use that tolerance as a writing target. "
            f"Additional writer feedback: {feedback or 'none'}. Return JSON only with this schema: "
            '{"blocks":[{"type":"heading|prose|dialogue|quote|divider","text":"..."}]}. '
            "The first block must be the actual chapter title from StoryMap, not an internal chapter ID.\n"
            f"Project direction: {json.dumps(project.direction, ensure_ascii=False)}\n"

            f"Writing context: {json.dumps(context, ensure_ascii=False)}"
        )

    @staticmethod
    def parse(text: str, nonce: str) -> tuple[NovelBlock, ...]:
        value = text.strip()
        fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
        if fenced:
            value = fenced[-1].strip()
        try:
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                raw = repair_json(value, schema=_Payload.model_json_schema())
            # Some OpenAI-compatible providers honor the item schema but omit
            # the outer object and return the chapter blocks as the root array.
            # Accept that lossless variant before normalizing individual blocks.
            if isinstance(raw, list):
                raw = {"blocks": raw}

            if isinstance(raw, dict) and isinstance(raw.get("blocks"), list):
                aliases = {
                    "paragraph": "prose",
                    "section": "prose",
                    "epistolary": "quote",
                    "document": "quote",
                    "letter": "quote",
                }
                normalized = []
                for item in raw["blocks"]:
                    if not isinstance(item, dict):
                        normalized.append(item)
                        continue
                    block_type = str(item.get("type") or "prose").lower()
                    normalized_type = aliases.get(block_type, block_type)
                    normalized.append(
                        {
                            "type": normalized_type,
                            # Divider is a structural boundary. Provider captions such
                            # as "***" or "scene break" must not leak into the domain
                            # text contract.
                            "text": ""
                            if normalized_type == "divider"
                            else item.get("text") or item.get("content"),
                        }
                    )
                raw = {**raw, "blocks": normalized}
            payload = _Payload.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
            raise NovelWriterError(
                "主笔返回的章节结构不完整，旧稿未受影响，请重新生成。"
            ) from error
        readable_blocks: list[_Block] = []
        for item in payload.blocks:
            if item.type != "prose":
                readable_blocks.append(item)
                continue
            parts = NovelChapterGenerator.split_readable_paragraphs(item.text)
            readable_blocks.extend(_Block(type="prose", text=part) for part in parts)
        prefix = nonce.replace("-", "")[:10]
        return tuple(
            NovelBlock(block_id=f"{prefix}-{index}", type=item.type, text=item.text)
            for index, item in enumerate(readable_blocks, 1)
        )

    @staticmethod
    def count_manuscript_units(blocks: tuple[NovelBlock, ...], creative_language: str) -> int:
        text = "\n".join(block.text for block in blocks)
        if creative_language.lower().startswith("en"):
            return len(re.findall(r"[\w]+(?:['’\-][\w]+)*", text, re.UNICODE))
        return len(re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9]+", text))

    @staticmethod
    def split_readable_paragraphs(text: str, max_words: int = 160) -> tuple[str, ...]:
        words = text.split()
        if len(words) <= max_words and len(text) <= 500:
            return (text,)
        sentences = [
            sentence.strip()
            for sentence in re.findall(
                r'.+?(?:[.!?。！？]["”’]?)(?=\s|$)|.+$',
                text,
                flags=re.DOTALL,
            )
            if sentence.strip()
        ]
        if len(sentences) < 2:
            return (text,)
        paragraphs: list[str] = []
        current: list[str] = []
        current_units = 0
        for sentence in sentences:
            sentence_units = len(sentence.split()) or len(sentence)
            if current and current_units + sentence_units > max_words:
                paragraphs.append(" ".join(current))
                current = []
                current_units = 0
            current.append(sentence)
            current_units += sentence_units
        if current:
            paragraphs.append(" ".join(current))
        return tuple(paragraphs)

    @staticmethod
    def _test_blocks(context: dict[str, object]) -> tuple[NovelBlock, ...]:
        chapter = dict(context["chapter"])
        title = str(chapter.get("title") or chapter.get("id") or "Chapter")
        beat = next(iter(chapter.get("beats") or []), {})
        objective = str(dict(beat).get("objective") or "The chapter advances its adopted StoryMap objective.")
        return (
            NovelBlock(block_id="test-h", type="heading", text=title),
            NovelBlock(block_id="test-p1", type="prose", text=objective),
            NovelBlock(block_id="test-p2", type="prose", text="The consequence remains open for the next chapter."),
        )

    async def _record_usage(
        self, reservation_id: str, tenant_id: str, run_id: str, result: AgentRuntimeResult
    ) -> None:
        await self.billing.record_model_call(
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            run_id=run_id,
            framework_event_id=f"novel-chapter:{run_id}",
            trace_id=run_id,
            agent_role="writer",
            model_key=result.model_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_price_per_million=result.input_price_per_million,
            output_price_per_million=result.output_price_per_million,
        )
