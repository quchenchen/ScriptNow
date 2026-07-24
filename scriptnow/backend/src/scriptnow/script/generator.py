import json
from contextlib import suppress
from uuid import uuid4

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RunStatus
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.script.domain import (
    BlueprintAnchorDraft,
    BlueprintDraft,
    StoryCoreDetails,
    StoryCoreDraft,
)
from scriptnow.script.story_map import Episode, Scene, ScriptStoryBeat


class ScriptGenerationError(RuntimeError):
    pass


class _Core(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=160)
    concept: str = Field(min_length=80)
    angles: tuple[str, ...] = Field(min_length=5, max_length=5)
    narrative_engine: tuple[str, ...] = Field(min_length=2, max_length=8)
    viewpoint_anchor: tuple[str, ...] = Field(min_length=1, max_length=6)
    pacing_recipe: tuple[str, ...] = Field(min_length=1, max_length=8)
    market_judgement: tuple[str, ...] = Field(min_length=1, max_length=6)


class _CorePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: tuple[_Core, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_distinct_candidates(self) -> "_CorePayload":
        if len({item.title.casefold().strip() for item in self.candidates}) != 3:
            raise ValueError("three distinct creative directions are required")
        return self


class _Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=2, max_length=120)
    kind: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    payload: dict[str, object]


class _BlueprintPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchors: tuple[_Anchor, ...] = Field(min_length=8, max_length=80)


class _Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=8)
    anchor_ids: tuple[str, ...] = Field(min_length=1, max_length=12)


class _Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    beats: tuple[_Beat, ...] = Field(min_length=1, max_length=12)


class _Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    scenes: tuple[_Scene, ...] = Field(min_length=1)


class _StoryMapPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodes: tuple[_Episode, ...] = Field(min_length=1)


class ScriptCreativeGenerator:
    """Let the configured Agent own semantics; keep only user-selected bounds in code."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)

    async def story_cores(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        feedback: str | None,
    ) -> tuple[StoryCoreDraft, ...]:
        prompt = f"""
你是剧本创意总监。依据用户在创建项目时提交的参数，生成三个真正不同、可以比较的完整故事方向。
不得补写成预置故事，不得改变媒介、语言、格式、叙事结构或用户边界。

项目参数：
{json.dumps(dict(project.direction), ensure_ascii=False)}
项目名称：{project.name}
修订反馈：{feedback or "无"}

只返回 JSON：
{{"candidates":[{{"title":"...","concept":"至少80字的具体故事机制","angles":["欲望","阻力","关系变化","终局代价","最终选择"],"narrative_engine":["..."],"viewpoint_anchor":["..."],"pacing_recipe":["..."],"market_judgement":["优势","风险"]}}]}}
数组必须恰好三个，且不是同一故事换标题。
""".strip()
        try:
            payload = _CorePayload.model_validate(
                await self._json(
                    tenant_id, project.id, "director", prompt, dict(project.direction)
                )
            )
        except ValidationError as error:
            raise ScriptGenerationError(
                f"创意总监返回的候选结构不完整：{error}"
            ) from error
        return tuple(
            StoryCoreDraft(
                title=item.title,
                concept=item.concept,
                angles=item.angles,
                details=StoryCoreDetails(
                    narrative_engine=item.narrative_engine,
                    viewpoint_anchor=item.viewpoint_anchor,
                    pacing_recipe=item.pacing_recipe,
                    market_judgement=item.market_judgement,
                ),
            )
            for item in payload.candidates
        )

    async def blueprint(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        story_core: dict[str, object],
        feedback: str | None,
    ) -> BlueprintDraft:
        prompt = f"""
你是剧本故事建筑师。根据已采纳故事方向与用户项目参数，建立可供 StoryMap 和写作引用的剧本蓝图。
内容必须针对本项目生成；不要使用示例人物、示例地点或固定情节。
至少覆盖：世界与规则、核心人物、人物关系、人物弧线、关键事件、伏笔。
每个锚点 id 使用稳定的英文命名空间，如 character:protagonist；payload 写具体、可执行的信息。

项目参数：{json.dumps(dict(project.direction), ensure_ascii=False)}
已采纳方向：{json.dumps(story_core, ensure_ascii=False)}
修订反馈：{feedback or "无"}

只返回 JSON：
{{"anchors":[{{"id":"character:protagonist","kind":"character","name":"...","payload":{{"description":"..."}}}}]}}
""".strip()
        try:
            payload = _BlueprintPayload.model_validate(
                await self._json(
                    tenant_id,
                    project.id,
                    "architect",
                    prompt,
                    {"direction": dict(project.direction), "story_core": story_core},
                )
            )
        except ValidationError as error:
            raise ScriptGenerationError(
                f"故事建筑师返回的蓝图结构不完整：{error}"
            ) from error
        return BlueprintDraft(
            anchors=tuple(
                BlueprintAnchorDraft(
                    id=item.id, kind=item.kind, name=item.name, payload=item.payload
                )
                for item in payload.anchors
            )
        )

    async def story_map(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        story_core: dict[str, object],
        anchors: list[dict[str, object]],
        feedback: str | None,
    ) -> tuple[Episode, ...]:
        direction = dict(project.direction)
        episode_count = self._positive(direction, "volume_one")
        scenes_per_episode = self._positive(direction, "volume_two")
        scene_minutes = self._positive(direction, "volume_three")
        duration_seconds = scene_minutes * 60
        anchor_ids = {str(item["id"]) for item in anchors}
        prompt = f"""
你是剧本结构师。创建 StoryMap。故事语义由你完成，但必须严格服从用户在前端确定的体量。
必须生成 {episode_count} 个篇章，每篇恰好 {scenes_per_episode} 场；每场目标时长由系统采用用户设定的 {scene_minutes} 分钟。
每个 beat 只能引用给定蓝图锚点，不得虚构 anchor id。

项目参数：{json.dumps(direction, ensure_ascii=False)}
已采纳方向：{json.dumps(story_core, ensure_ascii=False)}
蓝图锚点：{json.dumps(anchors, ensure_ascii=False)}
修订反馈：{feedback or "无"}

只返回 JSON：
{{"episodes":[{{"title":"...","scenes":[{{"title":"...","beats":[{{"objective":"具体行动与变化","anchor_ids":["..."]}}]}}]}}]}}
""".strip()
        try:
            payload = _StoryMapPayload.model_validate(
                await self._json(
                    tenant_id,
                    project.id,
                    "architect",
                    prompt,
                    {
                        "direction": direction,
                        "story_core": story_core,
                        "blueprint_anchors": anchors,
                    },
                )
            )
        except ValidationError as error:
            raise ScriptGenerationError(
                f"故事建筑师返回的 StoryMap 结构不完整：{error}"
            ) from error
        if len(payload.episodes) != episode_count:
            raise ScriptGenerationError("Agent 返回的篇章数量与用户设定不一致")
        episodes: list[Episode] = []
        for episode_index, episode in enumerate(payload.episodes, 1):
            if len(episode.scenes) != scenes_per_episode:
                raise ScriptGenerationError("Agent 返回的每篇场数与用户设定不一致")
            scenes: list[Scene] = []
            for scene_index, scene in enumerate(episode.scenes, 1):
                beats: list[ScriptStoryBeat] = []
                for beat_index, beat in enumerate(scene.beats, 1):
                    unknown = set(beat.anchor_ids) - anchor_ids
                    if unknown:
                        raise ScriptGenerationError(
                            f"Agent 引用了未知蓝图锚点：{', '.join(sorted(unknown))}"
                        )
                    beats.append(
                        ScriptStoryBeat(
                            id=f"beat-{episode_index}-{scene_index}-{beat_index}",
                            objective=beat.objective,
                            anchor_ids=beat.anchor_ids,
                        )
                    )
                scenes.append(
                    Scene(
                        id=f"scene-{episode_index}-{scene_index}",
                        ordinal=scene_index,
                        title=scene.title,
                        duration_seconds_target=duration_seconds,
                        beats=tuple(beats),
                    )
                )
            episodes.append(
                Episode(
                    id=f"episode-{episode_index}",
                    ordinal=episode_index,
                    title=episode.title,
                    scenes=tuple(scenes),
                )
            )
        return tuple(episodes)

    async def _json(
        self,
        tenant_id: str,
        project_id: str,
        role: str,
        prompt: str,
        context: dict[str, object],
    ) -> object:
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=f"script-agent:{uuid4()}",
        )
        await self.runs.transition(
            tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING
        )
        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
                role=role,
                content=prompt,
                context_snapshot=context,
            )
            try:
                payload = json.loads(result.text)
            except json.JSONDecodeError:
                payload = repair_json(result.text)
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            return payload
        except (AgentRuntimeError, ValidationError, ValueError, TypeError) as error:
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="script_generation_failed",
                )
            raise ScriptGenerationError(f"Agent 返回内容无法形成有效创作候选：{error}") from error

    @staticmethod
    def _positive(direction: dict[str, object], key: str) -> int:
        try:
            value = int(str(direction.get(key) or ""))
        except ValueError as error:
            raise ScriptGenerationError(f"项目缺少前端创作参数：{key}") from error
        if value <= 0:
            raise ScriptGenerationError(f"项目创作参数必须大于零：{key}")
        return value
