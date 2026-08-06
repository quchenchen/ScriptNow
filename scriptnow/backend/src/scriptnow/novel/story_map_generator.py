import json
import logging
import re
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from scriptnow.novel.domain import (
    NovelBlueprintAnchorModel,
    NovelBlueprintModel,
    NovelCandidateStatus,
    NovelStoryCoreCandidateModel,
)
from scriptnow.novel.story_map import Chapter, NovelStoryBeat, Volume
from scriptnow.platform.agent_runtime import (
    AgentRuntime,
    AgentRuntimeError,
    AgentRuntimeResult,
    AgentRuntimeTimeoutError,
)
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator

logger = logging.getLogger(__name__)


class NovelStoryMapGenerationError(RuntimeError):
    pass


class _Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=4, max_length=1_000)
    anchor_ids: tuple[str, ...] = Field(min_length=1, max_length=12)


class _Chapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    point_of_view: str | None = Field(default=None, max_length=500)
    beats: tuple[_Beat, ...] = Field(min_length=1, max_length=12)


class _Volume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    chapters: tuple[_Chapter, ...] = Field(min_length=1)


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    volumes: tuple[_Volume, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def titles_are_not_placeholders(self) -> "_Payload":
        titles = [
            chapter.title.strip().casefold()
            for volume in self.volumes
            for chapter in volume.chapters
        ]
        if len(titles) != len(set(titles)):
            raise ValueError("chapter titles must be distinct")
        return self


class NovelStoryMapGenerator:
    """Generate creative structure through the configured Architect Agent.

    Counts and word targets are user-owned project settings. The Agent owns titles,
    beats, POV choices and anchor usage. Stable IDs and ordinals are technical
    persistence details and are normalized by the server.
    """

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
        )

    async def generate(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        feedback: str | None,
    ) -> tuple[Volume, ...]:
        volume_count, chapters_per_volume, target_words = self._settings(project)
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project.id)
        architect = dict(dict(status["roles"])["architect"])
        if not architect.get("connected"):
            raise NovelStoryMapGenerationError(
                f"real architect runtime is unavailable: {architect.get('reason') or 'unknown'}"
            )
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"novel-story-map:{idempotency_key}",
        )
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            core = (
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project.id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            anchors = list(
                await session.scalars(
                    select(NovelBlueprintAnchorModel)
                    .join(NovelBlueprintModel, NovelBlueprintAnchorModel.blueprint_id == NovelBlueprintModel.id)
                    .where(NovelBlueprintModel.project_id == project.id)
                    .order_by(NovelBlueprintAnchorModel.anchor_key)
                )
            )
        if tenant is None or core is None or not anchors:
            raise NovelStoryMapGenerationError(
                "adopted direction and blueprint are required before StoryMap generation"
            )
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"novel-story-map:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=min(
                self.settings.novel_story_map_max_reserved_tokens,
                max(
                    self.settings.novel_story_map_min_reserved_tokens,
                    volume_count
                    * chapters_per_volume
                    * self.settings.novel_story_map_tokens_per_chapter,
                ),
            ),
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        try:
            volumes = await self._generate_single(
                tenant_id=tenant_id,
                run_id=run.id,
                project=project,
                core=core,
                anchors=anchors,
                volume_count=volume_count,
                chapters_per_volume=chapters_per_volume,
                target_words=target_words,
                feedback=feedback,
            )
        except (AgentRuntimeTimeoutError, NovelStoryMapGenerationError) as batch_fallback:
            logger.warning(
                "novel StoryMap single-shot failed, falling back to batched generation",
                extra={"run_id": run.id, "error": str(batch_fallback)},
            )
            volumes = await self._generate_batched(
                tenant_id=tenant_id,
                run_id=run.id,
                project=project,
                core=core,
                anchors=anchors,
                volume_count=volume_count,
                chapters_per_volume=chapters_per_volume,
                target_words=target_words,
                feedback=feedback,
            )
        except Exception as error:
            logger.exception(
                "novel StoryMap generation failed",
                extra={"run_id": run.id, "project_id": project.id},
            )
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="novel_story_map_failed",
                )
            if isinstance(error, NovelStoryMapGenerationError):
                raise
            if isinstance(error, AgentRuntimeError):
                raise NovelStoryMapGenerationError(str(error)) from error
            raise NovelStoryMapGenerationError(f"invalid architect StoryMap output: {error}") from error
        await self.billing.finalize(reservation.id)
        await self.runs.transition(
            tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
        )
        return volumes

    async def _generate_single(
        self,
        *,
        tenant_id: str,
        run_id: str,
        project: ProjectModel,
        core,
        anchors: list,
        volume_count: int,
        chapters_per_volume: int,
        target_words: int,
        feedback: str | None,
    ) -> tuple[Volume, ...]:
        result = await self.runtime.generate(
            tenant_id=tenant_id,
            run_id=run_id,
            role="architect",
            content=self._prompt(
                project=project,
                core=core,
                anchors=anchors,
                volume_count=volume_count,
                chapters_per_volume=chapters_per_volume,
                target_words=target_words,
                feedback=feedback,
            ),
            context_snapshot={
                "project_id": project.id,
                "creation_settings": {
                    "volume_count": volume_count,
                    "chapters_per_volume": chapters_per_volume,
                    "chapter_target_words": target_words,
                },
                "adopted_story_core_id": core.id,
                "blueprint_version": max(anchor.blueprint_id for anchor in anchors),
            },
        )
        payload = self.parse(result.text)
        return self.normalize(
            payload,
            volume_count=volume_count,
            chapters_per_volume=chapters_per_volume,
            target_words=target_words,
            valid_anchor_ids={item.anchor_key for item in anchors},
        )

    async def _generate_batched(
        self,
        *,
        tenant_id: str,
        run_id: str,
        project: ProjectModel,
        core,
        anchors: list,
        volume_count: int,
        chapters_per_volume: int,
        target_words: int,
        feedback: str | None,
    ) -> tuple[Volume, ...]:
        batch_size = self.settings.novel_story_map_batch_chapters
        per_call = max(batch_size // chapters_per_volume, 1) * chapters_per_volume
        total_chapters = volume_count * chapters_per_volume
        all_chapters: list[Chapter] = []
        for offset in range(0, total_chapters, per_call):
            chunk_count = min(per_call, total_chapters - offset)
            chunk_volumes = chunk_count // chapters_per_volume
            if chunk_count % chapters_per_volume:
                chunk_volumes += 1
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run_id,
                role="architect",
                content=self._prompt(
                    project=project,
                    core=core,
                    anchors=anchors,
                    volume_count=chunk_volumes,
                    chapters_per_volume=min(chapters_per_volume, chunk_count),
                    target_words=target_words,
                    feedback=(feedback or "") + f" (batch: chapters {offset+1}-{offset+chunk_count} of {total_chapters})",
                ),
                context_snapshot={
                    "project_id": project.id,
                    "batch": f"{offset+1}-{offset+chunk_count}",
                    "total_chapters": total_chapters,
                    "volume_count": chunk_volumes,
                    "chapters_per_volume": min(chapters_per_volume, chunk_count),
                    "chapter_target_words": target_words,
                },
            )
            payload = self.parse(result.text)
            chunk_vols = self.normalize(
                payload,
                volume_count=chunk_volumes,
                chapters_per_volume=min(chapters_per_volume, chunk_count),
                target_words=target_words,
                valid_anchor_ids={item.anchor_key for item in anchors},
            )
            for vol in chunk_vols:
                all_chapters.extend(vol.chapters)
        # Reassemble into original volume count
        volumes: list[Volume] = []
        chapter_idx = 0
        for vi in range(volume_count):
            vol_chapters = all_chapters[chapter_idx : chapter_idx + chapters_per_volume]
            volumes.append(Volume(
                id=f"v{vi+1}-batched",
                ordinal=vi + 1,
                title=f"Volume {vi + 1}",
                chapters=tuple(vol_chapters),
            ))
            chapter_idx += chapters_per_volume
        return tuple(volumes)

    @staticmethod
    def _settings(project: ProjectModel) -> tuple[int, int, int]:
        missing = []
        malformed = []
        for key in ("volume_one", "volume_two", "chapter_target_words"):
            raw = project.direction.get(key)
            if raw is None:
                missing.append(key)
                continue
            try:
                int(raw)
            except (TypeError, ValueError):
                malformed.append(f"{key}='{raw}' (expected integer)")
        if missing or malformed:
            parts = []
            if missing:
                parts.append(f"missing: {', '.join(missing)}")
            if malformed:
                parts.append(f"non-integer: {'; '.join(malformed)}")
            hint = (
                "project.direction must contain integer values: "
                "volume_one=<chapters>, volume_two=<chapters>, "
                "chapter_target_words=<words>"
            )
            raise NovelStoryMapGenerationError(f"{'; '.join(parts)}. {hint}")
        values = (
            int(project.direction["volume_one"]),
            int(project.direction["volume_two"]),
            int(project.direction["chapter_target_words"]),
        )
        if any(value < 1 for value in values):
            raise NovelStoryMapGenerationError(
                "volume count, chapters per volume and per-chapter word target must be positive"
            )
        return values

    @staticmethod
    def parse(text: str) -> _Payload:
        value = text.strip()
        fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
        if fenced:
            value = fenced[-1].strip()

        # Attempt 1: strict JSON parse
        first_error: str | None = None
        try:
            return _Payload.model_validate(json.loads(value))
        except ValidationError as error:
            first_error = str(error)
        except json.JSONDecodeError:
            pass

        # Attempt 2: JSON repair with schema
        try:
            return _Payload.model_validate(
                repair_json(value, schema=_Payload.model_json_schema())
            )
        except (ValidationError, ValueError, TypeError):
            pass

        # Attempt 3: extract volumes from any JSON structure
        try:
            raw = repair_json(value)
            if isinstance(raw, dict):
                raw_volumes = raw.get("volumes", raw.get("data", raw))
                if isinstance(raw_volumes, list):
                    cleaned_vols = []
                    for v in raw_volumes:
                        if not isinstance(v, dict):
                            continue
                        vol_title = str(v.get("title", v.get("name", "")))
                        raw_chs = v.get("chapters", v.get("items", []))
                        if not isinstance(raw_chs, list):
                            continue
                        cleaned_chs = []
                        for ch in raw_chs:
                            if not isinstance(ch, dict):
                                continue
                            cleaned_chs.append({
                                "id": str(ch.get("id", ch.get("title", ""))),
                                "title": str(ch.get("title", ch.get("name", ""))),
                                "beat": str(ch.get("beat", ch.get("summary", ""))),
                            })
                        if cleaned_chs:
                            cleaned_vols.append({"title": vol_title, "chapters": cleaned_chs})
                    if cleaned_vols:
                        return _Payload.model_validate({"volumes": cleaned_vols})
        except Exception:
            pass

        raise NovelStoryMapGenerationError(
            first_error or "StoryMap 格式需要整理，旧版本已保留，请重新生成。"
        )

    @staticmethod
    def normalize(
        payload: _Payload,
        *,
        volume_count: int,
        chapters_per_volume: int,
        target_words: int,
        valid_anchor_ids: set[str],
    ) -> tuple[Volume, ...]:
        if len(payload.volumes) != volume_count:
            raise NovelStoryMapGenerationError(
                f"Architect returned {len(payload.volumes)} volumes; project setting requires {volume_count}"
            )
        normalized: list[Volume] = []
        for volume_index, volume in enumerate(payload.volumes, 1):
            if len(volume.chapters) != chapters_per_volume:
                raise NovelStoryMapGenerationError(
                    f"volume {volume_index} returned {len(volume.chapters)} chapters; "
                    f"project setting requires {chapters_per_volume}"
                )
            chapters: list[Chapter] = []
            for chapter_index, chapter in enumerate(volume.chapters, 1):
                beats: list[NovelStoryBeat] = []
                for beat_index, beat in enumerate(chapter.beats, 1):
                    unknown = set(beat.anchor_ids) - valid_anchor_ids
                    if unknown:
                        raise NovelStoryMapGenerationError(
                            f"chapter {chapter_index} cites unknown blueprint anchors: "
                            f"{', '.join(sorted(unknown))}"
                        )
                    beats.append(
                        NovelStoryBeat(
                            id=f"beat-{volume_index}-{chapter_index}-{beat_index}",
                            objective=beat.objective,
                            anchor_ids=beat.anchor_ids,
                        )
                    )
                chapters.append(
                    Chapter(
                        id=f"chapter-{volume_index}-{chapter_index}",
                        ordinal=chapter_index,
                        title=chapter.title,
                        target_words=target_words,
                        point_of_view=chapter.point_of_view,
                        beats=tuple(beats),
                    )
                )
            normalized.append(
                Volume(
                    id=f"volume-{volume_index}",
                    ordinal=volume_index,
                    title=volume.title,
                    chapters=tuple(chapters),
                )
            )
        return tuple(normalized)

    @staticmethod
    def _prompt(
        *,
        project: ProjectModel,
        core: NovelStoryCoreCandidateModel,
        anchors: list[NovelBlueprintAnchorModel],
        volume_count: int,
        chapters_per_volume: int,
        target_words: int,
        feedback: str | None,
    ) -> str:
        anchor_data = [
            {
                "id": item.anchor_key,
                "kind": item.kind,
                "name": item.name,
                "payload": item.payload,
            }
            for item in anchors
        ]
        return (
            "Create a production-ready NOVEL StoryMap. Creative titles, chapter objectives, POV choices "
            "and blueprint-anchor placement must arise from the adopted direction and blueprint; do not use "
            "template stories or screenplay terminology. Obey the user's exact volume and chapter counts. "
            "Every chapter must change the story through an actionable objective, cite existing blueprint "
            "anchor IDs, and prepare or pay off later movement. Return JSON only.\n"
            f"Creative language: {project.direction.get('language') or 'zh-CN'}.\n"
            f"Narrative structure selected by user: {project.direction.get('structure') or 'custom'}.\n"
            f"Required volume count: {volume_count}.\n"
            f"Required chapters per volume: {chapters_per_volume}.\n"
            f"Per-chapter word target selected by user: {target_words}.\n"
            f"Adopted direction: {core.title}\nPremise: {core.premise}\n"
            f"Point of view proposal: {core.point_of_view}\n"
            f"Narrative constraints: {json.dumps(core.narrative_constraints, ensure_ascii=False)}\n"
            f"Blueprint anchors: {json.dumps(anchor_data, ensure_ascii=False)}\n"
            f"User revision feedback: {feedback or 'none'}\n"
            'Schema: {"volumes":[{"title":"...","chapters":[{"title":"...",'
            '"point_of_view":"...","beats":[{"objective":"...","anchor_ids":["existing:id"]}]}]}]}'
        )

    async def _record_usage(
        self, reservation_id: str, tenant_id: str, run_id: str, result: AgentRuntimeResult
    ) -> None:
        await self.billing.record_model_call(
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            run_id=run_id,
            framework_event_id=f"novel-story-map:{run_id}",
            trace_id=run_id,
            agent_role="architect",
            model_key=result.model_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_price_per_million=result.input_price_per_million,
            output_price_per_million=result.output_price_per_million,
        )
