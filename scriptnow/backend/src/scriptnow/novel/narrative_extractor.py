"""Extract chapter exit notes from generated content and creative graph data.

Uses existing creative_graph data + heuristics to identify hooks, traits,
and relationship changes without requiring an additional LLM call.
"""

import re
import uuid

from scriptnow.novel.narrative_state import ChapterExitNote, NarrativeHook, NarrativeState

# ── Hook detection heuristics ──────────────────────────────────────

HOOK_PATTERNS: dict[str, list[str]] = {
    "mystery": [
        r"(?:why|what|who|how) .{3,50}\?",
        r"(?:unsolved|unanswered|unexplained|mysterious)",
        r"(?:secret|hidden|buried|concealed)",
        r"(?:never told|never knew|never understood)",
    ],
    "foreshadowing": [
        r"(?:would later|would come to|would prove)",
        r"(?:odd|strange|peculiar|unusual) .{3,30}(?:way|manner|fashion)",
        r"(?:something (?:about|in|with|behind)) .{3,50}",
    ],
    "conflict": [
        r"(?:threatened|warned|vowed|swore|promised to)",
        r"(?:against|oppose|defy|challenge)",
        r"(?:owed|debt|obligation)",
    ],
    "character_secret": [
        r"(?:never told|never admitted|never confessed)",
        r"(?:if .{3,30} knew|if .{3,30} found out)",
        r"(?:real reason|true reason|actual reason)",
    ],
    "relationship_tension": [
        r"(?:unresolved|unspoken|unfinished).{3,30}(?:between|with)",
        r"(?:still .{3,30}(?:angry|hurt|afraid|resent|love))",
    ],
}


def _detect_hooks(text: str, chapter_id: str) -> list[NarrativeHook]:
    """Detect potential hooks in chapter prose using regex patterns."""
    hooks = []
    for kind, patterns in HOOK_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Deduplicate similar hooks
                snippet = match.group(0).strip()
                if len(snippet) > 10:
                    hook_id = f"{chapter_id}_{kind}_{uuid.uuid4().hex[:8]}"
                    hooks.append(
                        NarrativeHook(
                            hook_id=hook_id,
                            chapter_planted=chapter_id,
                            description=snippet[:200],
                            kind=kind,
                        )
                    )
                    break  # one match per pattern per chapter
    return hooks[-5:]  # limit to 5 hooks per chapter


def _detect_traits(text: str) -> list[str]:
    """Detect character trait statements."""
    traits = []
    patterns = [
        r"(?:\w+) (?:was|is|had become|had always been|had never been) (?:a |an |the )?([\w\s]{10,80})",
        r"(?:\w+) (?:could|could not|couldn't|refused to|chose to) ([\w\s]{10,80})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            trait = match.group(0).strip()
            if len(trait) > 10 and len(trait) < 200:
                traits.append(trait)
    return traits[-5:]  # limit to 5 traits


def _detect_events(text: str) -> list[str]:
    """Detect key events from paragraph openings."""
    events = []
    for match in re.finditer(r"(?:She|He|It|They|The|A|An|Her|His|Its|Their)\s.{20,200}\.", text):
        snippet = match.group(0).strip()
        if len(snippet) > 30:
            events.append(snippet)
    # Keep representative events
    step = max(1, len(events) // 3)
    return events[::step][:3]


# ── Main extraction ────────────────────────────────────────────────


def extract_chapter_exit_note(
    chapter_id: str,
    chapter_text: str,
    creative_graph_data: dict | None = None,
    word_count: int = 0,
) -> ChapterExitNote:
    """Extract a chapter exit note from generated prose.

    Args:
        chapter_id: e.g., "chapter-3-1"
        chapter_text: The full chapter plain text
        creative_graph_data: Optional creative graph data for richer extraction
        word_count: Estimated word count
    """
    hooks = _detect_hooks(chapter_text, chapter_id)
    traits = _detect_traits(chapter_text)
    events = _detect_events(chapter_text)
    relationship_changes: list[str] = []
    world_rules: list[str] = []

    # Use creative_graph data if available
    if creative_graph_data:
        nodes = creative_graph_data.get("nodes", [])
        edges = creative_graph_data.get("edges", [])

        # Relationship changes from edges of type "emotional" or "conflict"
        for edge in edges:
            if edge.get("type") in ("emotional", "conflict"):
                label = edge.get("label", "")[:150]
                if label:
                    relationship_changes.append(label)

        # World rules from nodes of type "rule" or "concept"
        for node in nodes:
            if node.get("type") in ("rule", "concept", "state"):
                summary = node.get("summary", "")[:150]
                if summary:
                    world_rules.append(summary)

    return ChapterExitNote(
        chapter_id=chapter_id,
        planted_hooks=hooks,
        established_traits=traits,
        world_rules_added=world_rules[-5:],
        relationship_changes=relationship_changes[-5:],
        key_events=events,
        word_count=word_count,
    )


# ── State storage ────────────────────────────────────────────────

# In-memory cache per project (reset on restart)
# Production: store as serialized JSON in AgentState or a dedicated DB column
_state_cache: dict[str, NarrativeState] = {}


def get_narrative_state(project_id: str) -> NarrativeState:
    """Get or create narrative state for a project."""
    if project_id not in _state_cache:
        _state_cache[project_id] = NarrativeState(project_id=project_id)
    return _state_cache[project_id]


def update_narrative_state(project_id: str, exit_note: ChapterExitNote) -> NarrativeState:
    """Record a chapter's exit note into the cumulative state."""
    state = get_narrative_state(project_id)
    state.add_chapter_exit(exit_note)
    return state
