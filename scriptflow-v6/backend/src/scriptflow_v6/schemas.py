from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RevisionBrief(BaseModel):
    goal: str = Field(min_length=1)
    scope: list[str] = []
    preserve: list[str] = []
    constraints: list[str] = []


class ContextPack(BaseModel):
    anchors: dict[str, Any] = {}
    source_refs: list[str] = []
    open_threads: list[str] = []


class CreateRevision(BaseModel):
    scene_id: int
    candidate_content: str = Field(min_length=1)
    brief: RevisionBrief
    context_pack: ContextPack = ContextPack()
    evidence: list[dict[str, Any]] = []
    impact: list[dict[str, Any]] = []


class RevisionView(BaseModel):
    id: int
    project_id: int
    scene_id: int
    status: Literal["candidate", "adopted", "rejected", "stale"]
    candidate_content: str
    brief: dict[str, Any]
    context_pack: dict[str, Any]
    evidence: list[dict[str, Any]]
    impact: list[dict[str, Any]]
    stale_reason: str


class LivingAssetCandidateView(BaseModel):
    id: int
    project_id: int
    revision_id: int
    asset_type: Literal["character_state", "relationship_change", "timeline_event", "foreshadow_event", "world_fact"]
    title: str
    proposed_value: dict[str, Any]
    evidence: list[dict[str, Any]]
    autonomy_level: str
    status: Literal["candidate", "adopted", "rejected"]


class CreateProject(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal_type: Literal["original-novel", "original-script", "adapt-novel", "adapt-script"]
    seed: str = ""
    genre: str = ""
    audience: str = ""
    source_name: str = ""
    source_type: Literal["none", "pasted_text", "file_reference"] = "none"
    source_content: str = ""
    source_file_name: str = ""
    seed_maturity: Literal["theme", "pitch", "synopsis", "outline", "draft"] = "pitch"
    medium_key: str = "vertical-short-drama"
    story_structure: str = "three-act"
    story_structure: str = "three-act"
    planning_mode: Literal["plan_first", "progressive", "import_outline"] = "plan_first"
    target_volume_count: int = Field(default=1, ge=1, le=20)
    target_chapter_count: int = Field(default=12, ge=1, le=500)
    target_episode_count: int = Field(default=3, ge=1, le=100)
    target_scenes_per_episode: int = Field(default=8, ge=1, le=100)
    target_words: int = Field(default=0, ge=0)
    target_minutes_per_episode: int = Field(default=0, ge=0, le=300)
    style_direction: str = ""
    creative_boundaries: list[str] = []


class ProjectPlanView(BaseModel):
    project_id: int
    creation_source: str
    delivery_medium: str
    seed_maturity: str
    planning_mode: str
    target_volume_count: int
    target_chapter_count: int
    target_episode_count: int
    target_scenes_per_episode: int
    target_words: int
    target_minutes_per_episode: int
    style_direction: str
    medium_key: str = "vertical-short-drama"
    creative_boundaries: list[str]
    status: str


class StoryMapUnitView(BaseModel):
    id: int
    unit_type: str
    ordinal: int
    global_ordinal: int
    title: str
    intent: str
    status: str
    target_length: int
    risk_count: int
    manuscript_unit_id: int | None


class StoryMapGroupView(BaseModel):
    id: int
    group_type: str
    ordinal: int
    title: str
    goal: str
    status: str
    units: list[StoryMapUnitView]


class StoryMapView(BaseModel):
    project_id: int
    delivery_medium: str
    groups: list[StoryMapGroupView]
    planned_units: int
    adopted_units: int


class StoryMapUnitUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    intent: str | None = None
    status: Literal["planned", "drafting", "candidate", "adopted", "needs_review"] | None = None


class CreateStoryMapUnit(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    intent: str = ""
    target_length: int = Field(default=0, ge=0)


class ReorderStoryMapUnits(BaseModel):
    ordered_unit_ids: list[int] = Field(min_length=1)


class ProjectPlanChange(BaseModel):
    target_volume_count: int | None = Field(default=None, ge=1, le=20)
    target_chapter_count: int | None = Field(default=None, ge=1, le=500)
    target_episode_count: int | None = Field(default=None, ge=1, le=100)
    target_scenes_per_episode: int | None = Field(default=None, ge=1, le=100)
    target_words: int | None = Field(default=None, ge=0)
    target_minutes_per_episode: int | None = Field(default=None, ge=0, le=300)
    planning_mode: Literal["plan_first", "progressive", "import_outline"] | None = None
    style_direction: str | None = None
    creative_boundaries: list[str] | None = None
    confirm_rebuild: bool = False


class ProjectPlanImpactView(BaseModel):
    current_units: int
    target_units: int
    protected_units: int
    units_added: int
    units_removed: int
    topology_changed: bool
    can_apply: bool
    requires_confirmation: bool
    warnings: list[str]


class StoryCoreView(BaseModel):
    id: int
    title: str
    logline: str
    dramatic_question: str
    protagonist: str
    conflict: str
    promise: str
    source_strategy: str
    status: str


class TaskView(BaseModel):
    id: int
    status: str
    goal: str
    agent_profile: str
    status_message: str
    candidates: list[StoryCoreView] = []


class ProjectPulseView(BaseModel):
    phase: str
    state: Literal["working", "waiting_user", "ready", "blocked", "complete"]
    headline: str
    detail: str
    needs_user: bool
    next_action: str
    capability_tier: str
    estimated_credits: int


class ProjectView(BaseModel):
    id: int
    title: str
    goal_type: str
    genre: str
    audience: str
    seed: str
    status: str
    adopted_story_core_id: int | None
    source_name: str = ""
    source_status: str = ""
    task: TaskView | None = None
    pulse: ProjectPulseView | None = None


class NarrativeEntityView(BaseModel):
    id: int
    entity_type: str
    name: str
    truth: dict[str, Any]
    current_state: dict[str, Any]
    frozen: bool
    source_label: str


class NarrativeThreadView(BaseModel):
    id: int
    thread_type: str
    title: str
    setup: str
    payoff_target: str
    status: str
    urgency: str
    source_label: str


class ContinuityAlertView(BaseModel):
    id: int
    alert_type: str
    severity: str
    message: str
    evidence: list[dict[str, Any]]
    status: str


class ContinuityView(BaseModel):
    project_id: int
    health: Literal["stable", "attention", "risk"]
    entities: list[NarrativeEntityView]
    threads: list[NarrativeThreadView]
    alerts: list[ContinuityAlertView]


class ContextPreviewView(BaseModel):
    ordinal: int
    target_label: str
    previous_anchor: dict[str, Any] | None
    characters: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    open_threads: list[dict[str, Any]]
    foreshadows: list[dict[str, Any]]
    directives: list[dict[str, Any]]
    memory_updates: list[dict[str, Any]]
    pending_memory_decisions: list[dict[str, Any]]
    required_story_facts: list[dict[str, Any]]
    warnings: list[str]


class CreateNarrativeEntity(BaseModel):
    entity_type: Literal["character", "organization"]
    name: str = Field(min_length=1, max_length=200)
    identity: str = ""
    emotion: str = "尚未定义"
    location: str = "尚未定义"
    goal: str = ""


class NarrativeRelationshipCommand(BaseModel):
    from_entity_id: int
    to_entity_id: int
    relationship_type: str = Field(min_length=1, max_length=48)
    description: str = ""
    story_time: str = ""


class NarrativeRelationshipView(BaseModel):
    id: int
    from_entity_id: int
    from_name: str
    to_entity_id: int
    to_name: str
    relationship_type: str
    status: str
    description: str
    story_time: str


class CreateCharacterIntroduction(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    identity: str = ""
    narrative_function: str = Field(min_length=1)
    voice: str = ""
    first_appearance_ordinal: int = Field(ge=1)
    relationship_to_entity_id: int | None = None
    relationship_type: str = ""
    relationship_description: str = ""


class CreateRelationshipChange(BaseModel):
    from_entity_id: int
    to_entity_id: int
    relationship_type: str = Field(min_length=1, max_length=48)
    objective_relationship: str = Field(min_length=1)
    from_perception: str = ""
    to_perception: str = ""
    hidden_information: str = ""
    effective_from_ordinal: int = Field(ge=1)


class CreateWorldRuleChange(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    rule: str = Field(min_length=1)
    dramatic_constraint: str = Field(min_length=1)
    exceptions: str = ""
    effective_from_ordinal: int = Field(ge=1)


class CreateForeshadowPlanChange(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    planting_method: str = Field(min_length=1)
    planned_plant_ordinal: int = Field(ge=1)
    planned_reinforce_ordinals: list[int] = Field(default_factory=list)
    planned_resolve_ordinal: int = Field(ge=1)
    resolution_intent: str = Field(min_length=1)


class StoryBibleImpactView(BaseModel):
    story_map_unit_id: int
    ordinal: int
    artifact_state: str
    proposed_action: str
    status: str


class StoryBibleChangeView(BaseModel):
    id: int
    project_id: int
    change_type: str
    title: str
    proposed: dict[str, Any]
    effective_from_ordinal: int
    status: Literal["candidate", "adopted", "rejected"]
    impacts: list[StoryBibleImpactView]
    unaffected_adopted_before: int


class CascadeRevisionView(BaseModel):
    id: int
    project_id: int
    change_id: int
    unit_id: int
    base_version: int
    original_content: str
    candidate_content: str
    rationale: str
    evidence: list[dict[str, Any]]
    status: Literal["candidate", "adopted", "rejected", "stale"]


class CreateForeshadow(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    thread_kind: Literal["foreshadow", "hook", "mystery", "plot_promise"] = "foreshadow"
    planned_plant_ordinal: int | None = None
    planned_resolve_ordinal: int | None = None
    importance: int = Field(default=5, ge=1, le=10)
    subtlety: int = Field(default=5, ge=1, le=10)
    remind_before_units: int = Field(default=2, ge=0, le=50)
    related_entity_ids: list[int] = []
    resolution_notes: str = ""


class ForeshadowTransition(BaseModel):
    action: Literal["queue", "plant", "reinforce", "partial_resolve", "resolve", "abandon"]
    manuscript_ordinal: int | None = None
    evidence: str = ""


class ForeshadowView(BaseModel):
    id: int
    title: str
    content: str
    thread_kind: str
    status: str
    planned_plant_ordinal: int | None
    actual_plant_ordinal: int | None
    planned_resolve_ordinal: int | None
    actual_resolve_ordinal: int | None
    importance: int
    subtlety: int
    remind_before_units: int
    related_entity_ids: list[int]
    resolution_notes: str
    urgency: Literal["normal", "attention", "urgent", "overdue"]
    events: list[dict[str, Any]]


class ManuscriptCandidateView(BaseModel):
    id: int
    unit_id: int
    task_id: int
    title: str
    content: str
    status: str
    context_pack: dict[str, Any]
    state_delta: dict[str, Any]
    thread_actions: list[dict[str, Any]]
    continuity_report: list[dict[str, Any]]


class ManuscriptUnitView(BaseModel):
    id: int
    scene_id: int | None = None
    unit_type: str
    ordinal: int
    title: str
    adopted_content: str
    status: str
    candidate: ManuscriptCandidateView | None = None


class ManuscriptDocumentView(BaseModel):
    unit_id: int
    project_id: int
    version: int
    content: str
    source: str
    metadata: dict[str, Any]


class SaveManuscriptDocument(BaseModel):
    base_version: int = Field(ge=1)
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManuscriptDocumentVersionView(BaseModel):
    version: int
    content: str
    source: str
    metadata: dict[str, Any]


class RestoreManuscriptDocument(BaseModel):
    base_version: int = Field(ge=1)
    restore_version: int = Field(ge=1)


ManuscriptEditMode = Literal["shorten", "expand", "polish", "dialogue", "pace", "custom"]


class CreateManuscriptAiEdit(BaseModel):
    base_version: int = Field(ge=1)
    selection_start: int = Field(ge=0)
    selection_end: int = Field(gt=0)
    selected_text: str = Field(min_length=1)
    mode: ManuscriptEditMode
    instruction: str = ""
    preserve: list[str] = []


class ManuscriptEditRevisionView(BaseModel):
    id: int
    project_id: int
    unit_id: int
    base_version: int
    selection_start: int
    selection_end: int
    selected_text: str
    replacement_text: str
    mode: ManuscriptEditMode
    instruction: str
    preserve: list[str]
    context_before: str
    context_after: str
    rationale: str
    status: Literal["candidate", "adopted", "rejected", "stale"]
    stale_reason: str


class ManuscriptImpactCandidateView(BaseModel):
    id: int
    project_id: int
    edit_revision_id: int
    unit_id: int
    impact_type: Literal["character_state", "relationship_change", "foreshadow_event", "world_fact"]
    title: str
    proposed_value: dict[str, Any]
    evidence: list[dict[str, Any]]
    status: Literal["candidate", "adopted", "rejected"]


class RuntimeStatusView(BaseModel):
    mode: Literal["platform", "demo"]
    available: bool
    capability_tier: str


class RuntimeTestView(BaseModel):
    ok: bool
    runtime: str
    model: str
    message: str


class CreateDirective(BaseModel):
    scope: Literal["next_task", "project_rule"]
    target_type: Literal["project", "manuscript_unit", "agent_task"] = "project"
    target_id: int | None = None
    lifetime: Literal["once", "unit", "project"] = "once"
    instruction: str = Field(min_length=1, max_length=4000)
    preserve: list[str] = []
    constraints: list[str] = []


class DirectiveView(BaseModel):
    id: int
    scope: str
    target_type: str
    target_id: int | None
    lifetime: str
    instruction: str
    preserve: list[str]
    constraints: list[str]
    status: str
    consumed_by_task_id: int | None
