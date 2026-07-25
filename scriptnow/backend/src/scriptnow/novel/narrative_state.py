"""Narrative State Machine — cumulative chapter-level memory for the Writer agent.

Progressive disclosure architecture:
  Layer 1 (always):     Current chapter beat + direction
  Layer 2 (summarized): Prior chapter summaries + open hooks count
  Layer 3 (expanded):   Active hooks, established traits, world rules
  Layer 4 (on-demand):  Full hook details, character profiles (from creative_graph)

The state machine tracks:
  - Open hooks (planted but not yet resolved story threads)
  - Resolved hooks (which chapter closed them)
  - Established traits (character attributes, relationship states, world rules)
  - Chapter exit notes (what was established/changed in each chapter)
"""

from dataclasses import dataclass, field


@dataclass
class NarrativeHook:
    """A story hook planted in one chapter to be resolved later."""

    hook_id: str
    chapter_planted: str  # which chapter planted it
    description: str  # what the hook is
    kind: str  # mystery, conflict, character_secret, relationship_tension, foreshadowing
    resolved_in: str | None = None  # which chapter resolved it (None = still open)
    resolution_note: str | None = None  # how it was resolved


@dataclass
class ChapterExitNote:
    """What a chapter established, changed, or left hanging."""

    chapter_id: str
    planted_hooks: list[NarrativeHook] = field(default_factory=list)
    resolved_hooks: list[str] = field(default_factory=list)  # hook_ids resolved
    established_traits: list[str] = field(default_factory=list)  # "character X is Y"
    world_rules_added: list[str] = field(default_factory=list)  # "the Warden can only..."
    relationship_changes: list[str] = field(default_factory=list)  # "Alice now distrusts Bob"
    revealed_secrets: list[str] = field(default_factory=list)
    key_events: list[str] = field(default_factory=list)  # one-line event summaries
    word_count: int = 0


@dataclass
class NarrativeState:
    """Accumulated narrative state across all chapters."""

    project_id: str
    chapters: list[ChapterExitNote] = field(default_factory=list)
    all_hooks: list[NarrativeHook] = field(default_factory=list)
    all_traits: dict[str, list[str]] = field(default_factory=dict)  # char_name -> traits

    @property
    def open_hooks(self) -> list[NarrativeHook]:
        return [h for h in self.all_hooks if h.resolved_in is None]

    @property
    def resolved_hooks(self) -> list[NarrativeHook]:
        return [h for h in self.all_hooks if h.resolved_in is not None]

    def add_chapter_exit(self, note: ChapterExitNote) -> None:
        self.chapters.append(note)
        for hook in note.planted_hooks:
            self.all_hooks.append(hook)
        # Mark resolved hooks
        for hook_id in note.resolved_hooks:
            for h in self.all_hooks:
                if h.hook_id == hook_id:
                    h.resolved_in = note.chapter_id
        # Accumulate traits
        for trait in note.established_traits:
            char_name = trait.split(" is ")[0].strip() if " is " in trait else "unknown"
            self.all_traits.setdefault(char_name, []).append(trait)

    def to_markdown(self, *, compact: bool = False) -> str:
        """Render state as progressive-disclosure markdown.

        compact=True: Layer 2 — only open hooks and key trait summary
        compact=False: Layer 3 — full details with chapter context
        """
        lines = []
        if compact:
            if self.open_hooks:
                lines.append("### Open Story Hooks")
                for h in self.open_hooks[-10:]:
                    lines.append(f"- [{h.kind}] {h.description[:200]} (planted in {h.chapter_planted})")
            if self.all_traits:
                lines.append("\n### Established Character Traits")
                for name, traits in list(self.all_traits.items())[-10:]:
                    lines.append(f"- **{name}**: {traits[-1]}")
            return "\n".join(lines) if lines else ""

        # Full mode
        for chapter in self.chapters[-6:]:
            lines.append(f"\n#### {chapter.chapter_id}")
            if chapter.key_events:
                events = "\n  ".join(chapter.key_events)
                lines.append(f"  Events: {events}")
            if chapter.planted_hooks:
                hooks = "\n  ".join(f"[{h.kind}] {h.description[:150]}" for h in chapter.planted_hooks)
                lines.append(f"  Hooks planted: {hooks}")
            if chapter.resolved_hooks:
                lines.append(f"  Hooks resolved: {', '.join(chapter.resolved_hooks)}")
            if chapter.established_traits:
                traits = "\n  ".join(chapter.established_traits)
                lines.append(f"  Traits established: {traits}")
            if chapter.world_rules_added:
                rules = "\n  ".join(chapter.world_rules_added)
                lines.append(f"  World rules: {rules}")
            if chapter.relationship_changes:
                changes = "\n  ".join(chapter.relationship_changes)
                lines.append(f"  Relationship changes: {changes}")
        return "\n".join(lines) if lines else ""

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "chapter_count": len(self.chapters),
            "open_hooks": len(self.open_hooks),
            "resolved_hooks": len(self.resolved_hooks),
            "total_traits": sum(len(v) for v in self.all_traits.values()),
        }
