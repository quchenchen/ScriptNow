from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    goal_type: Mapped[str] = mapped_column(String(40), default="original-script")
    genre: Mapped[str] = mapped_column(String(80), default="")
    audience: Mapped[str] = mapped_column(String(80), default="")
    seed: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="germinating")
    adopted_story_core_id: Mapped[int | None] = mapped_column(nullable=True)


class ProjectPlan(Base):
    __tablename__ = "project_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True, index=True)
    creation_source: Mapped[str] = mapped_column(String(24))
    delivery_medium: Mapped[str] = mapped_column(String(16))
    seed_maturity: Mapped[str] = mapped_column(String(24), default="pitch")
    planning_mode: Mapped[str] = mapped_column(String(24), default="plan_first")
    medium_key: Mapped[str] = mapped_column(String(40), default="vertical-short-drama")
    story_structure: Mapped[str] = mapped_column(String(40), default="three-act")
    target_volume_count: Mapped[int] = mapped_column(default=1)
    target_chapter_count: Mapped[int] = mapped_column(default=0)
    target_episode_count: Mapped[int] = mapped_column(default=0)
    target_scenes_per_episode: Mapped[int] = mapped_column(default=0)
    target_words: Mapped[int] = mapped_column(default=0)
    target_minutes_per_episode: Mapped[int] = mapped_column(default=0)
    style_direction: Mapped[str] = mapped_column(Text, default="")
    creative_boundaries_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="adopted")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class StoryMapGroup(Base):
    __tablename__ = "story_map_groups"
    __table_args__ = (UniqueConstraint("project_id", "group_type", "ordinal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    group_type: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(240))
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="planned")


class StoryMapUnit(Base):
    __tablename__ = "story_map_units"
    __table_args__ = (UniqueConstraint("group_id", "unit_type", "ordinal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("story_map_groups.id"), index=True)
    unit_type: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column()
    global_ordinal: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(240))
    intent: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="planned")
    target_length: Mapped[int] = mapped_column(default=0)
    risk_count: Mapped[int] = mapped_column(default=0)
    manuscript_unit_id: Mapped[int | None] = mapped_column(ForeignKey("manuscript_units.id"), nullable=True)


class SourceCanon(Base):
    __tablename__ = "source_canons"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(240), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="pasted_text")
    content: Mapped[str] = mapped_column(Text, default="")
    file_name: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentTask(Base):
    __tablename__ = "agent_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_profile: Mapped[str] = mapped_column(String(80))
    skill_name: Mapped[str] = mapped_column(String(120))
    skill_version: Mapped[str] = mapped_column(String(40))
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    autonomy_level: Mapped[str] = mapped_column(String(4), default="A2")
    context_pack_json: Mapped[str] = mapped_column(Text, default="{}")
    status_message: Mapped[str] = mapped_column(String(500), default="")
    error_code: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StoryCoreCandidate(Base):
    __tablename__ = "story_core_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    logline: Mapped[str] = mapped_column(Text)
    dramatic_question: Mapped[str] = mapped_column(Text)
    protagonist: Mapped[str] = mapped_column(Text)
    conflict: Mapped[str] = mapped_column(Text)
    promise: Mapped[str] = mapped_column(Text)
    source_strategy: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NarrativeEntity(Base):
    __tablename__ = "narrative_entities"
    __table_args__ = (UniqueConstraint("project_id", "entity_type", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    truth_json: Mapped[str] = mapped_column(Text, default="{}")
    current_state_json: Mapped[str] = mapped_column(Text, default="{}")
    frozen: Mapped[bool] = mapped_column(default=False)
    source_label: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class NarrativeThread(Base):
    __tablename__ = "narrative_threads"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    thread_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(240))
    setup: Mapped[str] = mapped_column(Text, default="")
    payoff_target: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planted", index=True)
    urgency: Mapped[str] = mapped_column(String(16), default="normal")
    source_label: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class NarrativeRelationship(Base):
    __tablename__ = "narrative_relationships"
    __table_args__ = (UniqueConstraint("project_id", "from_entity_id", "to_entity_id", "relationship_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    from_entity_id: Mapped[int] = mapped_column(ForeignKey("narrative_entities.id"), index=True)
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("narrative_entities.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), default="active")
    description: Mapped[str] = mapped_column(Text, default="")
    story_time: Mapped[str] = mapped_column(String(120), default="")
    source_label: Mapped[str] = mapped_column(String(120), default="manual")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class StoryBibleChange(Base):
    __tablename__ = "story_bible_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    change_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    proposed_json: Mapped[str] = mapped_column(Text)
    effective_from_ordinal: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StoryBibleImpact(Base):
    __tablename__ = "story_bible_impacts"
    __table_args__ = (UniqueConstraint("change_id", "story_map_unit_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("story_bible_changes.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    story_map_unit_id: Mapped[int] = mapped_column(ForeignKey("story_map_units.id"), index=True)
    ordinal: Mapped[int] = mapped_column()
    artifact_state: Mapped[str] = mapped_column(String(32))
    proposed_action: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="planned")


class CascadeRevision(Base):
    __tablename__ = "cascade_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("story_bible_changes.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("manuscript_units.id"), index=True)
    base_version: Mapped[int] = mapped_column()
    original_content: Mapped[str] = mapped_column(Text)
    candidate_content: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ForeshadowRecord(Base):
    __tablename__ = "foreshadow_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    thread_kind: Mapped[str] = mapped_column(String(32), default="foreshadow")
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    planned_plant_ordinal: Mapped[int | None] = mapped_column(nullable=True)
    actual_plant_ordinal: Mapped[int | None] = mapped_column(nullable=True)
    planned_resolve_ordinal: Mapped[int | None] = mapped_column(nullable=True)
    actual_resolve_ordinal: Mapped[int | None] = mapped_column(nullable=True)
    importance: Mapped[int] = mapped_column(default=5)
    subtlety: Mapped[int] = mapped_column(default=5)
    remind_before_units: Mapped[int] = mapped_column(default=2)
    related_entity_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_label: Mapped[str] = mapped_column(String(120), default="manual")
    resolution_notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ForeshadowEvent(Base):
    __tablename__ = "foreshadow_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    foreshadow_id: Mapped[int] = mapped_column(ForeignKey("foreshadow_records.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    manuscript_ordinal: Mapped[int | None] = mapped_column(nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContinuityAlert(Base):
    __tablename__ = "continuity_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="notice")
    message: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ManuscriptUnit(Base):
    __tablename__ = "manuscript_units"
    __table_args__ = (UniqueConstraint("project_id", "unit_type", "ordinal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_type: Mapped[str] = mapped_column(String(24))
    ordinal: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(240), default="")
    adopted_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="planned")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ManuscriptDocumentVersion(Base):
    __tablename__ = "manuscript_document_versions"
    __table_args__ = (UniqueConstraint("unit_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("manuscript_units.id"), index=True)
    version: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="manual_edit")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ManuscriptDocumentMetadataVersion(Base):
    __tablename__ = "manuscript_document_metadata_versions"
    __table_args__ = (UniqueConstraint("unit_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("manuscript_units.id"), index=True)
    version: Mapped[int] = mapped_column()
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ManuscriptEditRevision(Base):
    __tablename__ = "manuscript_edit_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("manuscript_units.id"), index=True)
    base_version: Mapped[int] = mapped_column()
    selection_start: Mapped[int] = mapped_column()
    selection_end: Mapped[int] = mapped_column()
    selected_text: Mapped[str] = mapped_column(Text)
    replacement_text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(32))
    instruction: Mapped[str] = mapped_column(Text, default="")
    preserve_json: Mapped[str] = mapped_column(Text, default="[]")
    context_before: Mapped[str] = mapped_column(Text, default="")
    context_after: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    stale_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ManuscriptImpactCandidate(Base):
    __tablename__ = "manuscript_impact_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    edit_revision_id: Mapped[int] = mapped_column(ForeignKey("manuscript_edit_revisions.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("manuscript_units.id"), index=True)
    impact_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    proposed_value_json: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ManuscriptCandidate(Base):
    __tablename__ = "manuscript_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("manuscript_units.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    context_pack_json: Mapped[str] = mapped_column(Text)
    state_delta_json: Mapped[str] = mapped_column(Text, default="{}")
    thread_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    continuity_report_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CreativeDirective(Base):
    __tablename__ = "creative_directives"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    instruction: Mapped[str] = mapped_column(Text)
    preserve_json: Mapped[str] = mapped_column(Text, default="[]")
    constraints_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    consumed_by_task_id: Mapped[int | None] = mapped_column(ForeignKey("agent_tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "scene_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    scene_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200), default="")
    adopted_content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CreativeRevision(Base):
    __tablename__ = "creative_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), index=True)
    base_hash: Mapped[str] = mapped_column(String(64))
    candidate_content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    brief_json: Mapped[str] = mapped_column(Text)
    context_pack_json: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    impact_json: Mapped[str] = mapped_column(Text, default="[]")
    stale_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LivingAssetCandidate(Base):
    __tablename__ = "living_asset_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("creative_revisions.id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    proposed_value_json: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    autonomy_level: Mapped[str] = mapped_column(String(4), default="A4")
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StoryArchitecture(Base):
    """Global narrative blueprint — bridges StoryCore to StoryMap."""
    __tablename__ = "story_architectures"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True, index=True)
    thesis: Mapped[str] = mapped_column(Text, default="")
    approach: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    agent_session_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class NarrativeArc(Base):
    """One narrative segment — e.g. 潜入(EP01-12), 对决(EP46-65)."""
    __tablename__ = "narrative_arcs"
    __table_args__ = (UniqueConstraint("architecture_id", "ordinal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    architecture_id: Mapped[int] = mapped_column(ForeignKey("story_architectures.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    ordinal: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(100))
    episode_start: Mapped[int] = mapped_column()
    episode_end: Mapped[int] = mapped_column()
    core_conflict: Mapped[str] = mapped_column(Text, default="")
    emotional_landing: Mapped[str] = mapped_column(Text, default="")
    protag_state: Mapped[str] = mapped_column(Text, default="")
    antag_state: Mapped[str] = mapped_column(Text, default="")
    must_have_json: Mapped[str] = mapped_column(Text, default="[]")
    foreshadow_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    target_minutes_per_episode: Mapped[int] = mapped_column(default=3)
    target_scenes_per_episode: Mapped[int] = mapped_column(default=3)
    target_words_per_scene: Mapped[int] = mapped_column(default=300)
