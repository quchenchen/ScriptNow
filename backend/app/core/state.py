"""
Agent State — LangGraph state definition for the creation pipeline.
"""
from typing import TypedDict, Optional, Annotated
from datetime import datetime


class AgentState(TypedDict, total=False):
    """Shared state across all Agents in the creation pipeline."""

    # Project identity
    project_id: str
    session_id: str

    # User input
    user_idea: str                    # 用户原始创意
    target_audience: str              # 目标受众
    genre_preference: list[str]       # 用户偏好的题材
    cultural_background: str          # 文化背景（国内/海外）
    target_markets: list[str]         # 目标市场

    # Stage tracking
    current_stage: str               # ideation/structure/writing/review/asset/prompt/done
    stage_history: list[dict]         # [{stage, timestamp, agent, status}]

    # Structure Agent outputs
    story_structure: Optional[dict]   # JSON: title, synopsis, characters, outlines
    structure_version: int

    # Writing Agent outputs
    episodes: list[dict]              # [{episode, title, scenes[], cliffhanger}]
    writing_version: int
    current_episode: int              # 当前正在写/审核的集数

    # Review Agent outputs
    review_results: list[dict]        # 每集审核结果
    overall_review: Optional[dict]    # 整体审核结果
    retry_count: int                  # Ralph Loop 重试次数
    revision_history: list[dict]      # 修改历史记录

    # Asset extraction outputs
    character_assets: list[dict]
    location_assets: list[dict]
    prop_assets: list[dict]
    continuity_ledger: list[dict]

    # Prompt generation outputs
    shot_prompts: list[dict]          # Seedance 2.0 提示词

    # Metadata
    started_at: str
    completed_at: Optional[str]
    errors: list[str]
    agent_logs: list[dict]            # [{agent, action, timestamp, detail}]


def create_initial_state(
    project_id: str,
    session_id: str,
    user_idea: str,
    target_audience: str = "男频",
    genre_preference: list[str] | None = None,
    cultural_background: str = "国内",
    target_markets: list[str] | None = None,
) -> AgentState:
    """Create initial state for a new creation session."""
    return AgentState(
        project_id=project_id,
        session_id=session_id,
        user_idea=user_idea,
        target_audience=target_audience,
        genre_preference=genre_preference or [],
        cultural_background=cultural_background,
        target_markets=target_markets or ["国内"],
        current_stage="ideation",
        stage_history=[],
        episodes=[],
        review_results=[],
        retry_count=0,
        revision_history=[],
        started_at=datetime.now().isoformat(),
        errors=[],
        agent_logs=[],
        structure_version=0,
        writing_version=0,
        current_episode=0,
    )
