import json
import logging
import re
from collections.abc import Callable
from contextlib import suppress
from typing import Literal, TypeVar
from uuid import uuid4

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from scriptnow.platform.agent_runtime import (
    AgentRuntime,
    AgentRuntimeError,
    AgentRuntimeResult,
)
from scriptnow.platform.billing import BillingService, ReservationView
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import (
    BlueprintAnchorDraft,
    BlueprintDraft,
    StoryCoreDetails,
    StoryCoreDraft,
)
from scriptnow.script.format_profiles import generation_instructions, scene_craft_instructions
from scriptnow.script.story_map import Episode, Scene, ScriptStoryBeat

logger = logging.getLogger(__name__)

ValidatedPayload = TypeVar("ValidatedPayload")

SCRIPT_BLUEPRINT_KINDS = frozenset(
    {"worldview", "character", "arc", "character_arc", "event", "foreshadow"}
)
SCRIPT_BLUEPRINT_KIND_ALIASES = {
    "world": "worldview",
    "world_rule": "worldview",
    "relationship": "character",
    "plot": "arc",
    "narrative_arc": "arc",
    "key_event": "event",
    "setup": "foreshadow",
    "payoff": "foreshadow",
}


class ScriptGenerationError(RuntimeError):
    pass


def normalize_blueprint_kind(kind: str) -> str:
    normalized = kind.strip().casefold().replace("-", "_").replace(" ", "_")
    normalized = SCRIPT_BLUEPRINT_KIND_ALIASES.get(normalized, normalized)
    if normalized not in SCRIPT_BLUEPRINT_KINDS:
        raise ValueError(f"unsupported script blueprint kind: {kind}")
    return normalized


class _Core(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=160)
    concept: str = Field(min_length=80)
    angles: tuple[str, ...] = Field(min_length=5, max_length=5)
    # Per-episode hook lists are budgeted against the adopted episode count by the
    # project-aware validator (_core_payload_validator). The 40-item ceiling is only
    # a runaway guard, not a format constraint.
    narrative_engine: tuple[str, ...] = Field(min_length=1, max_length=40)
    viewpoint_anchor: tuple[str, ...] = Field(min_length=1, max_length=6)
    pacing_recipe: tuple[str, ...] = Field(min_length=1, max_length=40)
    market_judgement: tuple[str, ...] = Field(min_length=1, max_length=6)


class _CorePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: tuple[_Core, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_distinct_candidates(self) -> "_CorePayload":
        if len({item.title.casefold().strip() for item in self.candidates}) != 3:
            raise ValueError("three distinct creative directions are required")
        return self


def _episode_hook_cap(project: ProjectModel) -> int:
    """Episode-shaped hook lists must fit the adopted episode count, never a fixed 8."""
    raw = dict(project.direction or {}).get("volume_one")
    try:
        episode_count = max(1, int(raw))
    except (TypeError, ValueError):
        return 8
    return max(8, min(episode_count, 40))


def _core_payload_validator(
    episode_hook_cap: int,
) -> Callable[[object], _CorePayload]:
    def validate(payload: object) -> _CorePayload:
        parsed = _CorePayload.model_validate(payload)
        for item in parsed.candidates:
            for field_name in ("narrative_engine", "pacing_recipe"):
                if len(getattr(item, field_name)) > episode_hook_cap:
                    raise ValueError(
                        f"{field_name} exceeds the {episode_hook_cap} episode budget; "
                        "merge per-episode hooks into structural beats"
                    )
        return parsed

    return validate


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
    # Provider metadata beside the domain payload is harmless. Nested StoryMap
    # objects remain strict so malformed episodes, scenes and beats still fail.
    model_config = ConfigDict(extra="ignore")

    episodes: tuple[_Episode, ...] = Field(min_length=1)


def _anchor_reference_signature(value: str) -> str:
    """Build an order-independent signature for a provider-formatted anchor ref."""

    tokens = re.findall(r"[^\W_]+", value.casefold().replace(":", "_"))
    tokens = [
        token
        for token in tokens
        if token not in SCRIPT_BLUEPRINT_KINDS and token not in SCRIPT_BLUEPRINT_KIND_ALIASES
    ]
    return "|".join(sorted(tokens))


def _anchor_aliases(anchors: list[dict[str, object]]) -> dict[str, str]:
    """Return only aliases that resolve to exactly one canonical blueprint id."""

    candidates: dict[str, set[str]] = {}
    for anchor in anchors:
        anchor_id = str(anchor["id"])
        values = (anchor_id, str(anchor.get("name") or ""))
        for value in values:
            signature = _anchor_reference_signature(value)
            if signature:
                candidates.setdefault(signature, set()).add(anchor_id)
    return {
        signature: next(iter(anchor_ids))
        for signature, anchor_ids in candidates.items()
        if len(anchor_ids) == 1
    }


def _validate_story_map_payload(value: object) -> _StoryMapPayload:
    """Accept a provider envelope while keeping the domain payload strict."""

    for _ in range(2):
        if not isinstance(value, dict) or "episodes" in value:
            break
        wrapped = next(
            (
                nested
                for key, nested in value.items()
                if re.sub(r"[^a-z]", "", str(key).casefold()) in {"storymap", "result", "data"}
                and isinstance(nested, dict)
            ),
            None,
        )
        if wrapped is None:
            break
        value = wrapped
    return _StoryMapPayload.model_validate(value)


def _validate_story_map_contract(
    value: object,
    *,
    episode_count: int,
    scenes_per_episode: int,
    anchor_ids: set[str],
    anchor_aliases: dict[str, str] | None = None,
) -> _StoryMapPayload:
    """Validate structure, user-selected bounds, and blueprint references."""

    payload = _validate_story_map_payload(value)
    if len(payload.episodes) != episode_count:
        raise ValueError("episode count does not match the project setting")
    for episode in payload.episodes:
        if len(episode.scenes) != scenes_per_episode:
            raise ValueError("scene count does not match the project setting")
        for scene in episode.scenes:
            for beat in scene.beats:
                canonical_ids: list[str] = []
                unknown: set[str] = set()
                for anchor_id in beat.anchor_ids:
                    if anchor_id in anchor_ids:
                        canonical_ids.append(anchor_id)
                        continue
                    signature = _anchor_reference_signature(anchor_id)
                    canonical = (anchor_aliases or {}).get(signature)
                    if canonical:
                        canonical_ids.append(canonical)
                    else:
                        unknown.add(anchor_id)
                if unknown:
                    raise ValueError("unknown blueprint anchor ids: " + ", ".join(sorted(unknown)))
                beat.anchor_ids = tuple(dict.fromkeys(canonical_ids))
    return payload


class _ScriptBlockPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["slugline", "action", "character", "dialogue", "transition"]
    text: str = Field(min_length=1)


class _SceneDocumentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: tuple[_ScriptBlockPayload, ...] = Field(min_length=4)


def _validate_scene_document_payload(value: object) -> _SceneDocumentPayload:
    """Accept the two semantically equivalent structured-output envelopes."""

    if isinstance(value, list):
        value = {"blocks": value}
    elif isinstance(value, dict) and "blocks" in value:
        # Provider-specific envelope metadata does not belong to the Script
        # document contract. The blocks themselves remain strictly validated.
        value = {"blocks": value["blocks"]}
    elif isinstance(value, dict) and isinstance(value.get("content"), list):
        blocks = list(value["content"])
        if value.get("slugline") and (
            not blocks or not isinstance(blocks[0], dict) or blocks[0].get("type") != "slugline"
        ):
            blocks.insert(0, {"type": "slugline", "text": value["slugline"]})
        value = {"blocks": blocks}
    return _SceneDocumentPayload.model_validate(value)


def _restore_embedded_scene_blocks(
    blocks: tuple[_ScriptBlockPayload, ...],
) -> tuple[_ScriptBlockPayload, ...]:
    """Restore an exact block array collapsed into one text field by JSON repair.

    Some OpenAI-compatible providers truncate an otherwise valid blocks array
    at a string boundary. ``json_repair`` can then preserve the remaining JSON
    source inside that block's text. We only restore the tail when it parses as
    the same strict block schema; otherwise the contamination remains visible
    and the domain validator rejects it.
    """

    restored: list[_ScriptBlockPayload] = []
    marker = '"},{"type":'
    for block in blocks:
        offset = block.text.find(marker)
        if offset < 0:
            restored.append(block)
            continue
        prefix = block.text[:offset]
        source = (
            '[{"type":'
            + json.dumps(block.type)
            + ',"text":'
            + json.dumps(prefix, ensure_ascii=False)
            + block.text[offset + 1 :]
            + "]"
        )
        try:
            nested = json.loads(source)
            restored.extend(_ScriptBlockPayload.model_validate(item) for item in nested)
        except (json.JSONDecodeError, ValidationError, TypeError):
            # A provider may leave ordinary quotation marks inside the
            # collapsed text unescaped. The block boundary is still explicit,
            # so recover on that boundary and strictly validate every item.
            parts = block.text.split(marker)
            recovered: list[_ScriptBlockPayload] = [
                _ScriptBlockPayload(type=block.type, text=parts[0])
            ]
            try:
                for index, part in enumerate(parts[1:], start=1):
                    block_type, text = part.split('","text":"', maxsplit=1)
                    block_type = block_type.removeprefix('"')
                    if index == len(parts) - 1:
                        if not text.endswith('"}'):
                            raise ValueError("collapsed block tail is incomplete")
                        text = text[:-2]
                    recovered.append(
                        _ScriptBlockPayload.model_validate({"type": block_type, "text": text})
                    )
            except (ValidationError, TypeError, ValueError):
                restored.append(block)
            else:
                restored.extend(recovered)
    return tuple(restored)


class ScriptCreativeGenerator:
    """Let the configured Agent own semantics; keep only user-selected bounds in code."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
        )

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
{{"candidates":[{{"title":"...","concept":"至少80字的具体故事机制","angles":["欲望","阻力","关系变化","终局代价","最终选择"],"narrative_engine":["因果推进机制，可用一至八条完整描述"],"viewpoint_anchor":["视角与信息策略"],"pacing_recipe":["关键节奏路径"],"market_judgement":["优势","风险"]}}]}}
数组必须恰好三个，且不是同一故事换标题。每个字段都必须提供完整、非空的字符串数组；narrative_engine 可用一条完整机制或多条互补机制表达。
""".strip()
        try:
            payload = await self._json(
                tenant_id,
                project.id,
                "director",
                prompt,
                dict(project.direction),
                validator=_core_payload_validator(_episode_hook_cap(project)),
            )
        except ValidationError as error:
            logger.warning("invalid script StoryCore payload: %s", error)
            raise ScriptGenerationError(
                "创意方向暂未形成完整候选，请保留当前设定并重新生成。"
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
        existing_anchors: list[dict[str, object]] | None = None,
        feedback: str | None,
    ) -> BlueprintDraft:
        revision_context = (
            "当前蓝图候选："
            + json.dumps(existing_anchors, ensure_ascii=False)
            + "\n必须在保留未被反馈否定的有效内容基础上修订，并返回完整蓝图，不能只返回差异。"
            if existing_anchors
            else "当前尚无蓝图候选，请从已采纳方向建立完整蓝图。"
        )
        prompt = f"""
你是剧本故事建筑师。根据已采纳故事方向与用户项目参数，建立可供 StoryMap 和写作引用的剧本蓝图。
内容必须针对本项目生成；不要使用示例人物、示例地点或固定情节。
至少覆盖：世界与规则、核心人物、人物关系、人物弧线、关键事件、伏笔。
kind 只能使用以下六个稳定值：worldview、character、arc、character_arc、event、foreshadow。
人物关系归入 character；世界规则归入 worldview；关键事件归入 event；伏笔埋设与回收归入 foreshadow。
每个锚点 id 使用稳定的英文命名空间，如 character:protagonist；payload 写具体、可执行的信息。

项目参数：{json.dumps(dict(project.direction), ensure_ascii=False)}
已采纳方向：{json.dumps(story_core, ensure_ascii=False)}
{revision_context}
修订反馈：{feedback or "无"}

只返回 JSON：
{{"anchors":[{{"id":"character:protagonist","kind":"character","name":"...","payload":{{"description":"..."}}}}]}}
字段名必须严格使用 id、kind、name、payload；禁止用 label 替代 name。
""".strip()
        context = {
            "direction": dict(project.direction),
            "story_core": story_core,
            "existing_blueprint_anchors": existing_anchors or [],
        }
        try:
            payload = await self._json(
                tenant_id,
                project.id,
                "architect",
                prompt,
                context,
                validator=lambda value: self._validate_blueprint_payload(
                    value,
                    existing_anchors=existing_anchors,
                ),
            )
        except (ValidationError, ValueError) as first_error:
            logger.warning("invalid script blueprint payload, retrying once: %s", first_error)
            correction_prompt = f"""
{prompt}

上一次输出已被系统拒绝，原因是结构契约错误或内容不属于当前项目。
请重新读取本消息中的项目参数、已采纳方向和当前蓝图候选，从头返回当前项目的完整蓝图。
必须保留当前候选中未被反馈否定的稳定锚点 id；不得引入其他项目的人物、地点、系统或情节。
字段名只能是 id、kind、name、payload，绝不能使用 label。
""".strip()
            try:
                payload = await self._json(
                    tenant_id,
                    project.id,
                    "architect",
                    correction_prompt,
                    {
                        **context,
                        "contract_retry": True,
                        "rejected_reason": str(first_error),
                    },
                    skills_enabled=False,
                    validator=lambda value: self._validate_blueprint_payload(
                        value,
                        existing_anchors=existing_anchors,
                    ),
                )
            except (ValidationError, ValueError) as error:
                logger.warning("invalid script blueprint payload after retry: %s", error)
                raise ScriptGenerationError(
                    "故事建筑师未能形成属于当前项目的完整蓝图，请保留现有候选后重试。"
                ) from error
        except ScriptGenerationError:
            raise
        except Exception as error:
            logger.exception("unexpected script blueprint generation failure")
            raise ScriptGenerationError("故事建筑师暂时无法完成蓝图生成，请稍后重试。") from error
        return BlueprintDraft(
            anchors=tuple(
                BlueprintAnchorDraft(
                    id=item.id,
                    kind=normalize_blueprint_kind(item.kind),
                    name=item.name,
                    payload=item.payload,
                )
                for item in payload.anchors
            )
        )

    @staticmethod
    def _validate_blueprint_payload(
        value: object,
        *,
        existing_anchors: list[dict[str, object]] | None,
    ) -> _BlueprintPayload:
        payload = _BlueprintPayload.model_validate(value)
        if existing_anchors:
            previous_ids = {
                str(item.get("id") or "").strip()
                for item in existing_anchors
                if str(item.get("id") or "").strip()
            }
            revised_ids = {item.id for item in payload.anchors}
            if previous_ids and previous_ids.isdisjoint(revised_ids):
                previous_terms = ScriptCreativeGenerator._blueprint_affinity_terms(existing_anchors)
                revised_text = json.dumps(
                    [item.model_dump(mode="json") for item in payload.anchors],
                    ensure_ascii=False,
                ).casefold()
                retained_terms = {
                    term for term in previous_terms if term.casefold() in revised_text
                }
                if len(retained_terms) >= min(2, len(previous_terms)):
                    return payload
                raise ValueError(
                    "revised blueprint does not retain stable ids or semantic anchors "
                    "from the current candidate"
                )
        return payload

    @staticmethod
    def _blueprint_affinity_terms(
        anchors: list[dict[str, object]],
    ) -> set[str]:
        terms: set[str] = set()
        for anchor in anchors:
            name = str(anchor.get("name") or "").strip()
            for term in re.split(r"[—\-：:·|/（）()，,；;\s]+", name):
                term = term.strip()
                if 2 <= len(term) <= 24:
                    terms.add(term)
        return terms

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
        missing = [k for k in ("volume_one", "volume_two", "volume_three") if k not in direction]
        if missing:
            raise ScriptGenerationError(
                f"项目缺少创作参数：{', '.join(missing)}。"
                f"volume_one=集数, volume_two=每集场数, volume_three=每场分钟数"
            )
        episode_count = self._positive(direction, "volume_one")
        scenes_per_episode = self._positive(direction, "volume_two")
        scene_minutes = self._positive(direction, "volume_three")
        duration_seconds = scene_minutes * 60
        anchor_ids = {str(item["id"]) for item in anchors}
        anchor_aliases = _anchor_aliases(anchors)
        anchor_refs = {
            f"A{index:02d}": str(anchor["id"]) for index, anchor in enumerate(anchors, 1)
        }
        anchor_aliases.update(
            {
                _anchor_reference_signature(reference): anchor_id
                for reference, anchor_id in anchor_refs.items()
            }
        )
        anchor_catalog = [
            {
                "ref": reference,
                "kind": anchor.get("kind"),
                "name": anchor.get("name"),
                "summary": anchor.get("payload"),
            }
            for reference, anchor in zip(anchor_refs, anchors, strict=True)
        ]
        prompt = f"""
你是剧本结构师。创建 StoryMap。故事语义由你完成，但必须严格服从用户在前端确定的体量。
必须生成 {episode_count} 个篇章，每篇恰好 {scenes_per_episode} 场；每场目标时长由系统采用用户设定的 {scene_minutes} 分钟。
每个 beat 只能引用给定蓝图锚点，不得虚构引用。
anchor_ids 字段只能填写锚点目录中的短引用 ref（例如 A01），不要填写名称或内部 id。

项目参数：{json.dumps(direction, ensure_ascii=False)}
已采纳方向：{json.dumps(story_core, ensure_ascii=False)}
蓝图锚点目录：{json.dumps(anchor_catalog, ensure_ascii=False)}
修订反馈：{feedback or "无"}

只返回 JSON：
{{"episodes":[{{"title":"...","scenes":[{{"title":"...","beats":[{{"objective":"具体行动与变化","anchor_ids":["A01"]}}]}}]}}]}}
""".strip()
        context = {
            "direction": direction,
            "story_core": story_core,
            "blueprint_anchors": anchors,
        }
        try:
            payload = await self._json(
                tenant_id,
                project.id,
                "architect",
                prompt,
                context,
                validator=lambda value: _validate_story_map_contract(
                    value,
                    episode_count=episode_count,
                    scenes_per_episode=scenes_per_episode,
                    anchor_ids=anchor_ids,
                    anchor_aliases=anchor_aliases,
                ),
            )
        except (ValidationError, ValueError) as first_error:
            logger.warning("invalid script StoryMap payload, retrying once: %s", first_error)
            correction_prompt = f"""
{prompt}

上一次输出未通过 StoryMap 结构校验。请重新返回当前项目的完整 StoryMap。
具体拒绝原因：{first_error}
顶层只能包含 episodes；不得增加 storymap、meta、result 或 data 包装层。
episodes 内必须完整包含每一篇的 scenes，以及每场的 beats。
篇章数与每篇场数必须服从项目参数；所有 anchor_ids 必须逐字复制锚点目录中的 A01、A02 等短引用。
""".strip()
            try:
                payload = await self._json(
                    tenant_id,
                    project.id,
                    "architect",
                    correction_prompt,
                    {
                        **context,
                        "contract_retry": True,
                        "rejected_reason": str(first_error),
                    },
                    skills_enabled=False,
                    validator=lambda value: _validate_story_map_contract(
                        value,
                        episode_count=episode_count,
                        scenes_per_episode=scenes_per_episode,
                        anchor_ids=anchor_ids,
                        anchor_aliases=anchor_aliases,
                    ),
                )
            except (ScriptGenerationError, ValidationError, ValueError) as error:
                logger.warning("invalid script StoryMap payload after retry: %s", error)
                raise ScriptGenerationError(
                    "故事建筑师未能形成完整的 StoryMap，请保留当前蓝图后重试。"
                ) from error
        episodes: list[Episode] = []
        for episode_index, episode in enumerate(payload.episodes, 1):
            scenes: list[Scene] = []
            for scene_index, scene in enumerate(episode.scenes, 1):
                beats: list[ScriptStoryBeat] = []
                for beat_index, beat in enumerate(scene.beats, 1):
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

    async def scene_document(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        scene: dict[str, object],
        context: dict[str, object],
        feedback: str | None,
        run_id: str | None = None,
    ) -> tuple[ScriptBlock, ...]:
        direction = dict(project.direction)
        format_rules = generation_instructions(str(direction.get("script_format") or "chinese"))
        craft_rules = scene_craft_instructions()
        prompt = f"""
你是本项目的剧本主笔。只写指定场次的候选正文，不得自动采纳，不得写下一场。
严格依据用户选择的创作语言、剧本格式、场次目标时长，以及已采纳蓝图、Story Beat 和此前已采纳场次。
内容必须可拍：用动作、对白、环境与视听细节呈现，不用小说式心理解释，不输出分析、思考过程或 Markdown。
保持角色、规则、伏笔和前后场连续性。目标时长是创作约束，不得用重复对白或冗余动作凑量。

戏剧场景契约（优先级高于格式）：
{craft_rules}

交付格式投影（不得取代戏剧判断）：
{format_rules}

风格锚点（照此风格书写，不是照抄内容；同风格的对白是自然完整句、画面是动词名词化的可拍描述、▲只标关键分镜）：
```
1-1 相府偏院·院墙外 清晨 外
出场人物：丫鬟甲、丫鬟乙
清晨薄雾笼罩着相府偏院，麻雀在灰瓦院墙上跳跃鸣叫。
丫鬟甲提着笸箩沿青石甬道走来，凑近丫鬟乙，压低嗓门。
丫鬟甲：你听说了没？秦姨娘院里那位，昨儿又晕过去了。
丫鬟乙左右张望一眼，缩着脖子接话。
丫鬟乙：（小声）这回可不是装的。脸白得跟纸似的，眼看就没气了。
▲【特写】半开的雕花窗棂内，纱帐微微晃动——有人醒了。
林昭宁：（OS，迷糊）嘶……昨晚是加班加到猝死了吗？
```

项目参数：{json.dumps(direction, ensure_ascii=False)}
当前场：{json.dumps(scene, ensure_ascii=False)}
创作上下文：{json.dumps(context, ensure_ascii=False)}
修订反馈：{feedback or "无"}

只返回 JSON：
{{"blocks":[{{"type":"slugline","text":"..." }},{{"type":"action","text":"..."}},{{"type":"character","text":"..."}},{{"type":"dialogue","text":"..."}}]}}
type 只能是 slugline、action、character、dialogue、transition。
""".strip()
        try:
            payload = await self._json(
                tenant_id,
                project.id,
                "writer",
                prompt,
                {"direction": direction, "scene": scene, "context": context},
                run_id=run_id,
                validator=_validate_scene_document_payload,
            )
        except ValidationError as error:
            logger.warning("invalid script scene payload: %s", error)
            raise ScriptGenerationError("主笔返回的场次候选结构不完整") from error
        normalized_blocks = _restore_embedded_scene_blocks(payload.blocks)
        unique = uuid4().hex[:8]
        return tuple(
            ScriptBlock(
                para_id=f"{unique}-{index}",
                type=item.type,
                text=item.text,
            )
            for index, item in enumerate(normalized_blocks, 1)
        )

    async def _json(
        self,
        tenant_id: str,
        project_id: str,
        role: str,
        prompt: str,
        context: dict[str, object],
        *,
        skills_enabled: bool = True,
        run_id: str | None = None,
        validator: Callable[[object], ValidatedPayload],
        max_attempts: int = 3,
    ) -> ValidatedPayload:
        manages_run = run_id is None
        run = (
            await self.runs.enqueue(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=f"script-agent:{uuid4()}",
            )
            if manages_run
            else await self.runs.status(tenant_id=tenant_id, run_id=run_id)
        )
        if run is None or (not manages_run and run.project_id != project_id):
            raise ScriptGenerationError("剧本生成运行不属于当前项目")
        if manages_run:
            await self.runs.transition(
                tenant_id=tenant_id,
                run_id=run.id,
                target=RunStatus.RUNNING,
            )
        reservation = await self._reserve(tenant_id=tenant_id, run_id=run.id)
        for attempt in range(1, max_attempts + 1):
            try:
                result = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    role=role,
                    content=prompt,
                    context_snapshot=context,
                    skills_enabled=skills_enabled,
                )
            except AgentRuntimeError as error:
                await self._release(reservation)
                if manages_run:
                    with suppress(Exception):
                        await self.runs.transition(
                            tenant_id=tenant_id,
                            run_id=run.id,
                            target=RunStatus.FAILED,
                            error_code="script_generation_failed",
                        )
                raise ScriptGenerationError(
                    f"Agent 返回内容无法形成有效创作候选：{error}"
                ) from error
            try:
                payload = json.loads(result.text)
            except json.JSONDecodeError:
                payload = repair_json(result.text)
            try:
                validated = validator(payload)
            except (ValidationError, ValueError, TypeError) as error:
                if attempt >= max_attempts:
                    await self._release(reservation)
                    if manages_run:
                        with suppress(Exception):
                            await self.runs.transition(
                                tenant_id=tenant_id,
                                run_id=run.id,
                                target=RunStatus.FAILED,
                                error_code="script_contract_invalid",
                            )
                    raise
                logger.warning(
                    "script JSON contract invalid, retrying with feedback: %s", error
                )
                prompt = (
                    prompt
                    + "\n\n[契约校验反馈] 上次返回未通过结构化校验，错误：\n"
                    + f"{str(error)[:1_500]}\n"
                    + "请修复后返回完整 JSON（不要只返回差异），严格匹配 output contract "
                    + "中每个数组的元素数量与类型约束。"
                )
                continue
            await self._settle(reservation, tenant_id, run.id, result, role)
            if manages_run:
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.SUCCEEDED,
                )
            return validated
        raise ScriptGenerationError("script contract validation exhausted")

    async def _reserve(self, *, tenant_id: str, run_id: str) -> ReservationView:
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            if tenant is None:
                raise ScriptGenerationError("租户不存在")
        return await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run_id,
            idempotency_key=f"script-agent:{run_id}",
            tier=tenant.tier,
            max_tokens=self.settings.script_agent_reserved_tokens,
        )

    async def _settle(
        self,
        reservation: ReservationView,
        tenant_id: str,
        run_id: str,
        result: AgentRuntimeResult,
        role: str,
    ) -> None:
        await self.billing.record_model_call(
            reservation_id=reservation.id,
            tenant_id=tenant_id,
            run_id=run_id,
            framework_event_id=f"script-agent:{run_id}",
            trace_id=run_id,
            agent_role=role,
            model_key=result.model_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_price_per_million=result.input_price_per_million,
            output_price_per_million=result.output_price_per_million,
        )
        await self.billing.finalize(reservation.id)

    async def _release(self, reservation: ReservationView | None) -> None:
        if reservation is None:
            return
        with suppress(Exception):
            await self.billing.release(reservation.id)

    @staticmethod
    def _positive(direction: dict[str, object], key: str) -> int:
        try:
            value = int(str(direction.get(key) or ""))
        except ValueError as error:
            raise ScriptGenerationError(f"项目缺少前端创作参数：{key}") from error
        if value <= 0:
            raise ScriptGenerationError(f"项目创作参数必须大于零：{key}")
        return value
