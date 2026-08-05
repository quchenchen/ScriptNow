"""Narrative State Machine — cumulative episode-level memory for Script agents.

Progressive disclosure architecture (mirrors Novel's NarrativeState):
  Layer 1 (always):     Current episode beat + creative direction
  Layer 2 (summarized): Prior episode summaries + open hooks count + paywall history
  Layer 3 (expanded):   Active hooks, character traits, relationship states, visual anchors
  Layer 4 (on-demand):  Full hook details, character profiles, cliffhanger library

Short-drama specific memory dimensions beyond Novel's model:
  - Paywall beat history (type, episode, intensity) — prevents fatigue
  - Hook type usage log — prevents repeating same hook pattern
  - Cliffhanger pattern library — tracks which patterns work per genre
  - Character visual anchors — ensures cross-episode consistency for image prompts
  - Emotional K-line snapshots — tracks suppression/release rhythm across episodes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── Hook types (from script-hook-generator) ──
HookKind = Literal[
    "identity_reveal",     # 身份揭露
    "relationship_crisis", # 关系危机
    "life_death",          # 生死悬念
    "wealth_lure",         # 财富诱惑
    "revenge_preview",     # 复仇预告
    "transformation",      # 变身/超自然
    "protection_declare",  # 保护宣言
]

# ── Paywall beat types (from script-paywall-designer) ──
PaywallBeatKind = Literal[
    "identity_reversal",    # 身份反转卡点
    "relationship_change",  # 关系变化卡点
    "information_gap",      # 信息差卡点
    "crisis_escalation",    # 危机升级卡点
    "unfulfilled_promise",  # 承诺未兑现卡点
]

# ── Cliffhanger types (from script-cliffhanger) ──
CliffhangerKind = Literal[
    "half_fulfillment",     # 半兑现爽点
    "unresolved_question",  # 未完成问题
    "identity_reversal_tease", # 身份反转预告
    "crisis_escalation",    # 危机升级
]

# ── Emotional direction ──
EmotionDirection = Literal["suppress", "release"]  # 压 / 放


@dataclass
class ScriptHook:
    """A narrative hook planted in one episode to be resolved later."""

    hook_id: str
    episode_id: str          # which episode planted it
    description: str         # what the hook is
    kind: HookKind
    resolved_in: str | None = None    # episode that resolved it
    resolution_note: str | None = None


@dataclass
class PaywallBeatRecord:
    """A paywall beat used in an episode — tracked to prevent fatigue."""

    episode_id: str
    kind: PaywallBeatKind
    description: str
    intensity: int = 5  # 1-10, how strong the "must watch next" pull is


@dataclass
class CharacterVisualAnchor:
    """Character visual traits for cross-episode image prompt consistency."""

    character_name: str
    core_appearance: str       # 核心外貌描述
    signature_features: list[str] = field(default_factory=list)  # 标志性特征（痣/疤痕/戒指/发型）
    costume_palette: str = ""  # 服装色系
    established_in: str = ""   # which episode established this


@dataclass
class EpisodeExitNote:
    """What an episode established, changed, or left hanging."""

    episode_id: str
    episode_number: int

    # Narrative changes
    planted_hooks: list[ScriptHook] = field(default_factory=list)
    resolved_hooks: list[str] = field(default_factory=list)  # hook_ids
    established_traits: list[str] = field(default_factory=list)  # "X is Y"
    relationship_changes: list[str] = field(default_factory=list) # "A now distrusts B"
    revealed_secrets: list[str] = field(default_factory=list)
    key_events: list[str] = field(default_factory=list)

    # Short-drama specific
    paywall_beats_used: list[PaywallBeatRecord] = field(default_factory=list)
    hook_type_used: HookKind | None = None           # opening hook type
    cliffhanger_kind: CliffhangerKind | None = None  # ending cliffhanger type
    cliffhanger_description: str = ""
    emotional_direction: EmotionDirection | None = None  # suppress or release
    emotional_intensity: int = 5  # 1-10

    # Production
    word_count: int = 0
    visual_anchors_established: list[CharacterVisualAnchor] = field(default_factory=list)


@dataclass
class ScriptNarrativeState:
    """Accumulated narrative state across all episodes of a short drama."""

    project_id: str
    genre: str = ""  # revenge/romance/counterattack/billionaire/wargod/werewolf
    total_episodes_target: int = 20

    episodes: list[EpisodeExitNote] = field(default_factory=list)
    all_hooks: list[ScriptHook] = field(default_factory=list)
    all_traits: dict[str, list[str]] = field(default_factory=dict)  # char_name -> traits
    character_anchors: dict[str, CharacterVisualAnchor] = field(default_factory=dict)

    @property
    def open_hooks(self) -> list[ScriptHook]:
        return [h for h in self.all_hooks if h.resolved_in is None]

    @property
    def resolved_hooks(self) -> list[ScriptHook]:
        return [h for h in self.all_hooks if h.resolved_in is not None]

    @property
    def paywall_history(self) -> list[PaywallBeatRecord]:
        return [pb for ep in self.episodes for pb in ep.paywall_beats_used]

    @property
    def hook_type_history(self) -> list[HookKind]:
        return [ep.hook_type_used for ep in self.episodes if ep.hook_type_used]

    @property
    def cliffhanger_history(self) -> list[tuple[str, CliffhangerKind]]:
        return [(ep.episode_id, ep.cliffhanger_kind) for ep in self.episodes if ep.cliffhanger_kind]

    @property
    def emotional_kline(self) -> list[tuple[int, EmotionDirection, int]]:
        """Returns (episode_number, direction, intensity) for K-line chart."""
        return [
            (ep.episode_number, ep.emotional_direction, ep.emotional_intensity)
            for ep in self.episodes
            if ep.emotional_direction
        ]

    def add_episode_exit(self, note: EpisodeExitNote) -> None:
        """Register an episode's narrative changes into accumulated state."""
        self.episodes.append(note)

        for hook in note.planted_hooks:
            self.all_hooks.append(hook)

        for hook_id in note.resolved_hooks:
            for h in self.all_hooks:
                if h.hook_id == hook_id:
                    h.resolved_in = note.episode_id

        for trait in note.established_traits:
            char_name = trait.split(" is ")[0].strip() if " is " in trait else "unknown"
            self.all_traits.setdefault(char_name, []).append(trait)

        for anchor in note.visual_anchors_established:
            self.character_anchors[anchor.character_name] = anchor

    # ─── Paywall fatigue detection ───

    def last_paywall_kinds(self, n: int = 3) -> list[PaywallBeatKind]:
        """Recent paywall beat types — used to avoid repetition."""
        history = self.paywall_history
        return [pb.kind for pb in history[-n:]]

    def paywall_fatigue_warning(self) -> str:
        """Generate warning if same paywall type used too many times consecutively."""
        recent = self.last_paywall_kinds(4)
        if len(recent) >= 3 and len(set(recent[-3:])) == 1:
            return f"⚠️ Paywall fatigue: same type '{recent[-1]}' used 3 times in a row. Consider switching."
        return ""

    # ─── Hook type rotation ───

    def last_hook_kinds(self, n: int = 3) -> list[HookKind]:
        return self.hook_type_history[-n:]

    def hook_repetition_warning(self) -> str:
        """Generate warning if same hook type repeated."""
        recent = self.last_hook_kinds(3)
        if len(recent) >= 2 and len(set(recent[-2:])) == 1:
            return f"⚠️ Hook repetition: opening hook type '{recent[-1]}' used in consecutive episodes."
        return ""

    # ─── Emotional rhythm check ───

    def emotion_rhythm_warning(self) -> str:
        """Check K-line for consecutive suppress/release violations."""
        recent = self.emotional_kline[-4:]
        if len(recent) < 3:
            return ""
        directions = [d for _, d, _ in recent]
        # 3+ consecutive same direction = fatigue
        if all(d == "suppress" for d in directions[-3:]):
            return "⚠️ Emotional fatigue: 3+ consecutive 'suppress' episodes. Audience needs a release."
        if all(d == "release" for d in directions[-3:]):
            return "⚠️ Emotional inflation: 3+ consecutive 'release' episodes. Build tension before next peak."
        return ""

    # ─── Serialization for persistence ───

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "genre": self.genre,
            "total_episodes_target": self.total_episodes_target,
            "episode_count": len(self.episodes),
            "open_hooks": len(self.open_hooks),
            "resolved_hooks": len(self.resolved_hooks),
            "total_traits": sum(len(v) for v in self.all_traits.values()),
            "character_count": len(self.character_anchors),
        }

    # ─── Markdown rendering for context injection ───

    def to_markdown(self, *, compact: bool = False) -> str:
        """Render state as progressive-disclosure markdown.

        compact=True (Layer 2): open hooks + trait summary + fatigue warnings
        compact=False (Layer 3): full details with episode context
        """
        lines: list[str] = []

        if compact:
            # Open hooks
            if self.open_hooks:
                lines.append("### 📌 Open Story Hooks")
                for h in self.open_hooks[-10:]:
                    lines.append(f"- [{h.kind}] {h.description[:200]} (planted ep.{h.episode_id})")

            # Character traits
            if self.all_traits:
                lines.append("\n### 👤 Character Traits")
                for name, traits in list(self.all_traits.items())[-10:]:
                    lines.append(f"- **{name}**: {traits[-1]}")

            # Visual anchors
            if self.character_anchors:
                lines.append("\n### 🎨 Character Visual Anchors")
                for name, anchor in self.character_anchors.items():
                    features = ", ".join(anchor.signature_features[:3])
                    lines.append(f"- **{name}**: {anchor.core_appearance[:120]}")
                    if features:
                        lines.append(f"  Signature: {features}")

            # Paywall history summary
            recent_paywalls = self.last_paywall_kinds(5)
            if recent_paywalls:
                lines.append(f"\n### 💰 Recent Paywall Beats: {', '.join(recent_paywalls)}")

            # Hook rotation
            recent_hooks = self.last_hook_kinds(5)
            if recent_hooks:
                lines.append(f"### 🪝 Recent Opening Hooks: {', '.join(recent_hooks)}")

            # Warnings
            warnings = [
                w for w in [
                    self.paywall_fatigue_warning(),
                    self.hook_repetition_warning(),
                    self.emotion_rhythm_warning(),
                ] if w
            ]
            if warnings:
                lines.append("\n### ⚠️ Rhythm Warnings")
                for w in warnings:
                    lines.append(w)

            return "\n".join(lines) if lines else ""

        # Full mode — per-episode details
        for ep in self.episodes[-6:]:
            lines.append(f"\n#### Episode {ep.episode_number} ({ep.episode_id})")
            if ep.emotional_direction:
                direction_icon = "🔵 压" if ep.emotional_direction == "suppress" else "🔴 放"
                lines.append(f"  {direction_icon} intensity={ep.emotional_intensity}")
            if ep.key_events:
                events = "\n  ".join(ep.key_events)
                lines.append(f"  Events: {events}")
            if ep.planted_hooks:
                hooks = "\n  ".join(
                    f"[{h.kind}] {h.description[:150]}" for h in ep.planted_hooks
                )
                lines.append(f"  Hooks planted: {hooks}")
            if ep.resolved_hooks:
                lines.append(f"  Hooks resolved: {', '.join(ep.resolved_hooks)}")
            if ep.paywall_beats_used:
                pbs = ", ".join(f"{pb.kind}" for pb in ep.paywall_beats_used)
                lines.append(f"  Paywall beats: {pbs}")
            if ep.hook_type_used:
                lines.append(f"  Opening hook: {ep.hook_type_used}")
            if ep.cliffhanger_kind:
                lines.append(f"  Cliffhanger: {ep.cliffhanger_kind} — {ep.cliffhanger_description[:120]}")
            if ep.established_traits:
                traits = "\n  ".join(ep.established_traits)
                lines.append(f"  Traits: {traits}")
            if ep.relationship_changes:
                changes = "\n  ".join(ep.relationship_changes)
                lines.append(f"  Relationships: {changes}")

        return "\n".join(lines) if lines else ""

    # ─── Serialization for AgentState persistence ───

    def serialize(self) -> dict[str, object]:
        """Serialize to JSON-compatible dict for AgentState storage."""

        def _hook_to_dict(h: ScriptHook) -> dict:
            return {
                "hook_id": h.hook_id,
                "episode_id": h.episode_id,
                "description": h.description,
                "kind": h.kind,
                "resolved_in": h.resolved_in,
                "resolution_note": h.resolution_note,
            }

        def _paywall_to_dict(pb: PaywallBeatRecord) -> dict:
            return {
                "episode_id": pb.episode_id,
                "kind": pb.kind,
                "description": pb.description,
                "intensity": pb.intensity,
            }

        def _anchor_to_dict(a: CharacterVisualAnchor) -> dict:
            return {
                "character_name": a.character_name,
                "core_appearance": a.core_appearance,
                "signature_features": a.signature_features,
                "costume_palette": a.costume_palette,
                "established_in": a.established_in,
            }

        def _exit_to_dict(ep: EpisodeExitNote) -> dict:
            return {
                "episode_id": ep.episode_id,
                "episode_number": ep.episode_number,
                "planted_hooks": [_hook_to_dict(h) for h in ep.planted_hooks],
                "resolved_hooks": ep.resolved_hooks,
                "established_traits": ep.established_traits,
                "relationship_changes": ep.relationship_changes,
                "revealed_secrets": ep.revealed_secrets,
                "key_events": ep.key_events,
                "paywall_beats_used": [_paywall_to_dict(pb) for pb in ep.paywall_beats_used],
                "hook_type_used": ep.hook_type_used,
                "cliffhanger_kind": ep.cliffhanger_kind,
                "cliffhanger_description": ep.cliffhanger_description,
                "emotional_direction": ep.emotional_direction,
                "emotional_intensity": ep.emotional_intensity,
                "word_count": ep.word_count,
                "visual_anchors_established": [_anchor_to_dict(a) for a in ep.visual_anchors_established],
            }

        return {
            "project_id": self.project_id,
            "genre": self.genre,
            "total_episodes_target": self.total_episodes_target,
            "episodes": [_exit_to_dict(ep) for ep in self.episodes],
        }

    @classmethod
    def deserialize(cls, data: dict[str, object]) -> ScriptNarrativeState:
        """Restore from serialized AgentState dict."""
        state = cls(
            project_id=str(data.get("project_id", "")),
            genre=str(data.get("genre", "")),
            total_episodes_target=int(data.get("total_episodes_target", 20)),
        )
        for ep_data in data.get("episodes", []) or []:
            ep_data = dict(ep_data) if isinstance(ep_data, dict) else {}
            ep_num_raw = ep_data.get("episode_number", 0)
            ep_num = int(ep_num_raw) if isinstance(ep_num_raw, int | str) else 0
            note = EpisodeExitNote(
                episode_id=str(ep_data.get("episode_id", "")),
                episode_number=ep_num,
                resolved_hooks=[str(h) for h in ep_data.get("resolved_hooks", []) or []],
                established_traits=[str(t) for t in ep_data.get("established_traits", []) or []],
                relationship_changes=[str(r) for r in ep_data.get("relationship_changes", []) or []],
                revealed_secrets=[str(s) for s in ep_data.get("revealed_secrets", []) or []],
                key_events=[str(e) for e in ep_data.get("key_events", []) or []],
                hook_type_used=ep_data.get("hook_type_used"),
                cliffhanger_kind=ep_data.get("cliffhanger_kind"),
                cliffhanger_description=str(ep_data.get("cliffhanger_description", "")),
                emotional_direction=ep_data.get("emotional_direction"),
                emotional_intensity=int(ep_data.get("emotional_intensity", 5)),
                word_count=int(ep_data.get("word_count", 0)),
            )
            # Restore hooks
            for h_data in ep_data.get("planted_hooks", []) or []:
                h_data = dict(h_data) if isinstance(h_data, dict) else {}
                note.planted_hooks.append(ScriptHook(
                    hook_id=str(h_data.get("hook_id", "")),
                    episode_id=str(h_data.get("episode_id", "")),
                    description=str(h_data.get("description", "")),
                    kind=h_data.get("kind", "identity_reveal"),
                    resolved_in=h_data.get("resolved_in"),
                    resolution_note=h_data.get("resolution_note"),
                ))
            # Restore paywall beats
            for pb_data in ep_data.get("paywall_beats_used", []) or []:
                pb_data = dict(pb_data) if isinstance(pb_data, dict) else {}
                note.paywall_beats_used.append(PaywallBeatRecord(
                    episode_id=str(pb_data.get("episode_id", "")),
                    kind=pb_data.get("kind", "identity_reversal"),
                    description=str(pb_data.get("description", "")),
                    intensity=int(pb_data.get("intensity", 5)),
                ))
            # Restore visual anchors
            for a_data in ep_data.get("visual_anchors_established", []) or []:
                a_data = dict(a_data) if isinstance(a_data, dict) else {}
                note.visual_anchors_established.append(CharacterVisualAnchor(
                    character_name=str(a_data.get("character_name", "")),
                    core_appearance=str(a_data.get("core_appearance", "")),
                    signature_features=list(a_data.get("signature_features", []) or []),
                    costume_palette=str(a_data.get("costume_palette", "")),
                    established_in=str(a_data.get("established_in", "")),
                ))
            state.add_episode_exit(note)
        return state
