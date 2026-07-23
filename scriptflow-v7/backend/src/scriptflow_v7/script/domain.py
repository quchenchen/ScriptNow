from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from scriptflow_v7.platform.database import Base
from scriptflow_v7.platform.models import new_id, utc_now


class CandidateStatus(StrEnum):
    ACTIVE = "active"
    ADOPTED = "adopted"
    EXPIRED = "expired"


class RevisionStatus(StrEnum):
    CANDIDATE = "candidate"
    ADOPTED = "adopted"
    SUPERSEDED = "superseded"


class StoryCoreDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    narrative_engine: tuple[str, ...]
    viewpoint_anchor: tuple[str, ...]
    pacing_recipe: tuple[str, ...]
    market_judgement: tuple[str, ...]


class StoryCoreDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=160)
    concept: str = Field(min_length=10)
    angles: tuple[str, ...] = Field(min_length=5, max_length=5)
    details: StoryCoreDetails


class BlueprintAnchorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: str
    name: str
    payload: dict[str, object] = Field(default_factory=dict)


class BlueprintDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anchors: tuple[BlueprintAnchorDraft, ...] = Field(min_length=1)


class ScriptStoryCoreCandidateModel(Base):
    __tablename__ = "script_story_core_candidates"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "generation", "ordinal", name="uq_script_core_generation_ordinal"
        ),
        UniqueConstraint(
            "project_id", "idempotency_key", "ordinal", name="uq_script_core_request_ordinal"
        ),
        Index("ix_script_core_project_status", "project_id", "status"),
        Index(
            "uq_script_core_one_adopted",
            "project_id",
            unique=True,
            sqlite_where=text("status = 'adopted'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    concept: Mapped[str] = mapped_column(String, nullable=False)
    angles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.ACTIVE)
    revision_feedback: Mapped[str | None] = mapped_column(String)


class ScriptBlueprintModel(Base):
    __tablename__ = "script_blueprints"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_script_blueprint_version"),
        Index(
            "uq_script_blueprint_one_adopted",
            "project_id",
            unique=True,
            sqlite_where=text("adopted = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    story_core_candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("script_story_core_candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    adopted: Mapped[bool] = mapped_column(default=True)


class ScriptBlueprintCandidateModel(Base):
    __tablename__ = "script_blueprint_candidates"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_script_blueprint_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    story_core_candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("script_story_core_candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    draft: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.ACTIVE)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class ScriptBlueprintAnchorModel(Base):
    __tablename__ = "script_blueprint_anchors"
    __table_args__ = (
        UniqueConstraint("blueprint_id", "anchor_key", name="uq_script_blueprint_anchor_key"),
        Index("ix_script_blueprint_anchor_kind", "blueprint_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    blueprint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("script_blueprints.id", ondelete="CASCADE"), nullable=False
    )
    anchor_key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class ScriptStructureCandidateModel(Base):
    __tablename__ = "script_structure_candidates"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_script_structure_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_episodes: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    impact: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.ACTIVE)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class ScriptDocumentRevisionModel(Base):
    __tablename__ = "script_document_revisions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "scene_id", "revision_number", name="uq_script_scene_revision"
        ),
        UniqueConstraint("project_id", "idempotency_key", name="uq_script_document_request"),
        Index("ix_script_document_scene_status", "project_id", "scene_id", "status"),
        Index(
            "uq_script_document_one_adopted",
            "project_id",
            "scene_id",
            unique=True,
            sqlite_where=text("status = 'adopted'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str] = mapped_column(String(120), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    base_revision_id: Mapped[str | None] = mapped_column(String(36))
    blocks: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RevisionStatus.CANDIDATE)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class ScriptSnapshotContentModel(Base):
    __tablename__ = "script_snapshot_contents"

    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    documents: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class ScriptExportManifestModel(Base):
    __tablename__ = "script_export_manifests"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_script_export_request"),
        Index("ix_script_exports_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    script_format: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
