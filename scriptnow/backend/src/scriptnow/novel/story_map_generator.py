import json
import logging
import re
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from scriptnow.novel.domain import (
    NovelBlueprintAnchorModel,
    NovelCandidateStatus,
    NovelStoryCoreCandidateModel,
)
from scriptnow.novel.story_map import Chapter, NovelStoryBeat, Volume
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
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
        self.runtime = AgentRuntime(database, settings)
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
                    .where(NovelBlueprintAnchorModel.project_id == project.id)
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
            max_tokens=min(48_000, max(12_000, volume_count * chapters_per_volume * 1_200)),
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
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
            volumes = self.normalize(
                payload,
                volume_count=volume_count,
                chapters_per_volume=chapters_per_volume,
                target_words=target_words,
                valid_anchor_ids={item.anchor_key for item in anchors},
            )
            await self._record_usage(reservation.id, tenant_id, run.id, result)
            await self.billing.finalize(reservation.id)
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            return volumes
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

    @staticmethod
    def _settings(project: ProjectModel) -> tuple[int, int, int]:
        try:
            values = (
                int(project.direction["volume_one"]),
                int(project.direction["volume_two"]),
                int(project.direction["chapter_target_words"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NovelStoryMapGenerationError(
                "set volume count, chapters per volume and per-chapter word target first"
            ) from error
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
        try:
            return _Payload.model_validate(json.loads(value))
        except json.JSONDecodeError:
            try:
                return _Payload.model_validate(
                    repair_json(value, schema=_Payload.model_json_schema())
                )
            except (ValidationError, ValueError, TypeError) as error:
                raise NovelStoryMapGenerationError(
                    "StoryMap 格式需要整理，旧版本已保留，请重新生成。"
                ) from error
        except ValidationError as error:
            raise NovelStoryMapGenerationError(str(error)) from error

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
