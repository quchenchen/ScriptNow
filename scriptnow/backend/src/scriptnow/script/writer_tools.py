"""AgentScope tools for the Script Writer agent.

Uses ScriptNarrativeState for cumulative episode-level memory
and creative-graph for entity lookups.  Mirrors novel/writer_tools.py
in structure and tool philosophy.
"""

from __future__ import annotations

from functools import partial

from agentscope.tool import FunctionTool

from scriptnow.platform.database import Database
from scriptnow.script.narrative_state import ScriptNarrativeState


async def get_prior_episode_summaries(
    database: Database,
    *,
    project_id: str,
    max_episodes: int = 6,
) -> str:
    """Return condensed summaries of the most recently written episodes.

    Use this before drafting to understand what happened in the story so far
    and which hooks / paywall beats / emotional states are active.

    Args:
        project_id: The project UUID.
        max_episodes: Maximum number of prior episode summaries to return (default 6).

    Returns:
        A markdown-formatted string with episode summaries and narrative state.
    """
    state = await _load_state(database, project_id)
    if not state or not state.episodes:
        return "No prior episode summaries available."

    return state.to_markdown(compact=True)


async def get_open_hooks(
    database: Database,
    *,
    project_id: str,
) -> str:
    """Get all unresolved narrative hooks (planted but not yet resolved).

    Use this before writing a new episode to ensure:
    - You don't forget to progress or resolve open hooks
    - You don't plant contradictory new hooks
    - You know which story threads need attention

    Args:
        project_id: The project UUID.

    Returns:
        A markdown list of open hooks with their episode origins.
    """
    state = await _load_state(database, project_id)
    if not state or not state.open_hooks:
        return "No open hooks — all planted threads have been resolved."

    lines = ["## Open Story Hooks"]
    for h in state.open_hooks[-15:]:
        lines.append(f"- [{h.kind}] {h.description[:200]} (planted ep.{h.episode_id})")
    return "\n".join(lines)


async def get_character_traits(
    database: Database,
    *,
    project_id: str,
    character_name: str | None = None,
) -> str:
    """Get accumulated character traits across all episodes.

    Use this to maintain character consistency — check established traits
    before writing a character's dialogue or actions in a new episode.

    Args:
        project_id: The project UUID.
        character_name: Optional filter by character name. If omitted, returns all.

    Returns:
        A markdown list of character traits, optionally filtered.
    """
    state = await _load_state(database, project_id)
    if not state or not state.all_traits:
        return "No character traits accumulated yet."

    if character_name:
        traits = state.all_traits.get(character_name, [])
        if not traits:
            return f"No traits recorded for '{character_name}'."
        lines = [f"## Traits: {character_name}"]
        for t in traits[-10:]:
            lines.append(f"- {t}")
        return "\n".join(lines)

    lines = ["## All Character Traits"]
    for name, traits in list(state.all_traits.items()):
        if traits:
            lines.append(f"- **{name}**: {traits[-1]}")
    return "\n".join(lines)


async def get_paywall_and_hook_history(
    database: Database,
    *,
    project_id: str,
) -> str:
    """Get recent paywall beat and hook type history with fatigue warnings.

    Use this before designing this episode's hook and paywall to avoid
    repeating the same patterns.

    Args:
        project_id: The project UUID.

    Returns:
        Markdown with recent paywall types, hook types, and rhythm warnings.
    """
    state = await _load_state(database, project_id)
    if not state or not state.episodes:
        return "No paywall/hook history available — this may be the first episode."

    lines = []
    recent_paywalls = state.last_paywall_kinds(5)
    if recent_paywalls:
        lines.append(f"**Recent paywall beats**: {', '.join(recent_paywalls)}")
    recent_hooks = state.last_hook_kinds(5)
    if recent_hooks:
        lines.append(f"**Recent opening hooks**: {', '.join(recent_hooks)}")

    warnings = [
        w for w in (
            state.paywall_fatigue_warning(),
            state.hook_repetition_warning(),
            state.emotion_rhythm_warning(),
        ) if w
    ]
    if warnings:
        lines.append("\n### ⚠️ Warnings")
        lines.extend(warnings)

    return "\n".join(lines) if lines else "No history yet."


async def get_episode_beat(
    database: Database,
    *,
    project_id: str,
    episode_id: str,
) -> str:
    """Get the StoryMap beat for a specific episode.

    Use this to retrieve the planned outline before drafting.

    Args:
        project_id: The project UUID.
        episode_id: The episode identifier.

    Returns:
        The episode beat description from the adopted StoryMap.
    """
    from sqlalchemy import select as sa_select

    from scriptnow.script.domain import ScriptStoryMapModel

    async with database.session() as session:
        story_map = (
            await session.scalars(
                sa_select(ScriptStoryMapModel).where(
                    ScriptStoryMapModel.project_id == project_id,
                )
            )
        ).one_or_none()

    if story_map is None:
        return "No adopted StoryMap found."

    for vol in story_map.volumes:
        for ep in vol.get("chapters", vol.get("episodes", [])):
            if str(ep.get("id")) == episode_id:
                title = ep.get("title", "untitled")
                beat = ep.get("beat", "")
                return f"## Episode Beat: {title}\n{beat}"

    return f"Episode {episode_id} not found in StoryMap."


# ── Internal helpers ────────────────────────────────────────────────

async def _load_state(database: Database, project_id: str) -> ScriptNarrativeState | None:
    """Load persisted narrative state from agent_states table, or return fresh."""
    from sqlalchemy import select as sa_select

    from scriptnow.platform.models import AgentStateModel

    async with database.session() as session:
        row = (
            await session.scalars(
                sa_select(AgentStateModel).where(
                    AgentStateModel.project_id == project_id,
                    AgentStateModel.role_key == "writer",
                )
            )
        ).one_or_none()

    if row is None or not row.serialized_state:
        return None

    try:
        return ScriptNarrativeState.deserialize(row.serialized_state)
    except Exception:
        return None


# ── Tool registry ───────────────────────────────────────────────────

WRITER_TOOLS: dict[str, callable] = {
    "get_prior_episode_summaries": get_prior_episode_summaries,
    "get_open_hooks": get_open_hooks,
    "get_character_traits": get_character_traits,
    "get_paywall_and_hook_history": get_paywall_and_hook_history,
    "get_episode_beat": get_episode_beat,
}


# ── Toolkit factory (for DomainToolProvider protocol) ────────────────

def create_writer_toolkit(database: Database, *, project_id: str = "") -> list[object]:
    """Create AgentScope FunctionTool instances for the Script Writer agent.

    Returns a list of ToolBase-compatible objects.
    """
    return [
        FunctionTool(
            partial(get_prior_episode_summaries, database),
            name="get_prior_episode_summaries",
            description="Get prior episode summaries with narrative state (hooks, traits, paywall history). Use before drafting to understand story so far.",
        ),
        FunctionTool(
            partial(get_open_hooks, database),
            name="get_open_hooks",
            description="Get all unresolved narrative hooks across episodes. Use to track which story threads need progression or resolution.",
        ),
        FunctionTool(
            partial(get_character_traits, database),
            name="get_character_traits",
            description="Get accumulated character traits. Optionally filter by name. Use to maintain consistency when writing a character.",
        ),
        FunctionTool(
            partial(get_paywall_and_hook_history, database),
            name="get_paywall_and_hook_history",
            description="Get recent hook/paywall history with fatigue warnings. Use to avoid repeating patterns when designing this episode.",
        ),
        FunctionTool(
            partial(get_episode_beat, database),
            name="get_episode_beat",
            description="Get the planned StoryMap beat for a specific episode. Use before drafting to know the creative direction.",
        ),
    ]


# ── Self-registration with platform tool provider ───────────────────

def _register() -> None:
    from scriptnow.platform.tool_provider import register_tool_provider

    register_tool_provider("script", _ScriptToolProvider())


class _ScriptToolProvider:
    def create_writer_tools(self, database: Database, *, project_id: str = "") -> list[object]:
        return create_writer_toolkit(database)


_register()
