"""Medium profiles — centralized conventions for each creative delivery format."""
from __future__ import annotations

from typing import NamedTuple


class MediumProfile(NamedTuple):
    key: str
    label: str
    label_en: str
    # --- Default sizing ---
    default_episodes: int
    default_scenes_per_episode: int
    default_minutes_per_episode: int
    words_per_minute: int
    # --- Creative conventions ---
    shot_guidance: str
    scene_pacing: str
    agent_tone_guidance: str


PROFILES: dict[str, MediumProfile] = {
    "vertical-short-drama": MediumProfile(
        key="vertical-short-drama",
        label="竖屏短剧",
        label_en="Vertical Short Drama",
        default_episodes=80,
        default_scenes_per_episode=3,
        default_minutes_per_episode=3,
        words_per_minute=200,
        shot_guidance="以人物近景和特写为主，偶尔中景。极少远景和复杂调度。",
        scene_pacing="每场1分钟，3场/集。每集结尾设钩子。冲突以对话和微表情推进。",
        agent_tone_guidance="对白要尖锐、有潜台词。动作描写极简。场景空间控制在2-3个室内。",
    ),
    "horizontal-web-series": MediumProfile(
        key="horizontal-web-series",
        label="横屏网剧",
        label_en="Horizontal Web Series",
        default_episodes=24,
        default_scenes_per_episode=6,
        default_minutes_per_episode=30,
        words_per_minute=180,
        shot_guidance="标准影视构图。允许中远景、群戏和场景切换。",
        scene_pacing="每场3-5分钟。有A/B故事线交错。每集有独立起承转合。",
        agent_tone_guidance="对白自然但有信息量。场景描写可适度丰富。允许多角色同时在场。",
    ),
    "feature-film": MediumProfile(
        key="feature-film",
        label="电影剧本",
        label_en="Feature Film",
        default_episodes=1,
        default_scenes_per_episode=45,
        default_minutes_per_episode=110,
        words_per_minute=150,
        shot_guidance="标准电影剧本格式。三幕结构。允许全镜头范围。",
        scene_pacing="每场2-4分钟。有明确的三幕转折点。情绪弧线完整。",
        agent_tone_guidance="按标准剧本格式输出。场景标题、动作描写、对白分行。人物介绍附简要备注。",
    ),
    "animated-series": MediumProfile(
        key="animated-series",
        label="动画剧本",
        label_en="Animated Series",
        default_episodes=12,
        default_scenes_per_episode=4,
        default_minutes_per_episode=20,
        words_per_minute=180,
        shot_guidance="画面描述可以更夸张和视觉化。允许超现实转场。",
        scene_pacing="每场3-5分钟。节奏可快于真人剧。视觉笑点和动作戏可占比更高。",
        agent_tone_guidance="画面描述优先于对白。允许夸张的动作指示。人物表情和肢体语言要具体。",
    ),
    "novel": MediumProfile(
        key="novel",
        label="长篇小说",
        label_en="Novel",
        default_episodes=0,
        default_scenes_per_episode=0,
        default_minutes_per_episode=0,
        words_per_minute=0,
        shot_guidance="",
        scene_pacing="每章3000-8000字。叙事文本，不设场景约束。",
        agent_tone_guidance="小说叙事文本。允许内心独白、环境描写和叙事评论。章节标题自定。",
    ),
    "short-story": MediumProfile(
        key="short-story",
        label="短篇小说",
        label_en="Short Story",
        default_episodes=0,
        default_scenes_per_episode=0,
        default_minutes_per_episode=0,
        words_per_minute=0,
        shot_guidance="",
        scene_pacing="全文5000-30000字。单一叙事视角。",
        agent_tone_guidance="短篇小说结构。聚焦单一事件或人物弧线。节奏紧凑。",
    ),
    "interactive-narrative": MediumProfile(
        key="interactive-narrative",
        label="互动叙事",
        label_en="Interactive Narrative",
        default_episodes=1,
        default_scenes_per_episode=12,
        default_minutes_per_episode=60,
        words_per_minute=200,
        shot_guidance="每个节点场景完整独立。过渡文本引导选择。",
        scene_pacing="每节点1-3分钟阅读量。2-4个分支选项。多条结局路径。",
        agent_tone_guidance="第二人称叙事。选项要体现有意义的选择，不能都是等价替换。结局要有差异性。",
    ),
}


def get_profile(medium_key: str) -> MediumProfile:
    return PROFILES.get(medium_key, PROFILES["vertical-short-drama"])


def profile_for_goal(goal_type: str) -> MediumProfile:
    """Heuristic: derive medium profile from goal_type."""
    if goal_type.endswith("novel"):
        return PROFILES["novel"]
    if "adapt" in goal_type:
        return PROFILES["horizontal-web-series"]
    return PROFILES["vertical-short-drama"]


def profile_labels() -> list[dict]:
    return [{"key": p.key, "label": p.label, "label_en": p.label_en} for p in PROFILES.values()]
