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


class NovelCandidateStatus(StrEnum):
    ACTIVE = "active"
    ADOPTED = "adopted"
    EXPIRED = "expired"


class NovelRevisionStatus(StrEnum):
    CANDIDATE = "candidate"
    ADOPTED = "adopted"
    SUPERSEDED = "superseded"


class NovelStoryCoreDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=160)
    premise: str = Field(min_length=10)
    point_of_view: str = Field(min_length=1)
    narrative_constraints: tuple[str, ...] = Field(min_length=1)
    angles: tuple[str, ...] = Field(min_length=5, max_length=5)


class NovelBlueprintAnchorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: str
    name: str
    payload: dict[str, object] = Field(default_factory=dict)


class NovelBlueprintDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anchors: tuple[NovelBlueprintAnchorDraft, ...] = Field(min_length=1)


class NovelStoryCoreCandidateModel(Base):
    __tablename__ = "novel_story_core_candidates"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "generation", "ordinal", name="uq_novel_core_generation_ordinal"
        ),
        UniqueConstraint(
            "project_id", "idempotency_key", "ordinal", name="uq_novel_core_request_ordinal"
        ),
        Index("ix_novel_core_project_status", "project_id", "status"),
        Index(
            "uq_novel_core_one_adopted",
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
    premise: Mapped[str] = mapped_column(String, nullable=False)
    point_of_view: Mapped[str] = mapped_column(String(120), nullable=False)
    narrative_constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    angles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=NovelCandidateStatus.ACTIVE)
    revision_feedback: Mapped[str | None] = mapped_column(String)


class NovelBlueprintCandidateModel(Base):
    __tablename__ = "novel_blueprint_candidates"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_novel_blueprint_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    story_core_candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novel_story_core_candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    draft: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=NovelCandidateStatus.ACTIVE)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class NovelBlueprintModel(Base):
    __tablename__ = "novel_blueprints"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_novel_blueprint_version"),
        Index(
            "uq_novel_blueprint_one_adopted",
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
        ForeignKey("novel_story_core_candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    adopted: Mapped[bool] = mapped_column(default=True)


class NovelBlueprintAnchorModel(Base):
    __tablename__ = "novel_blueprint_anchors"
    __table_args__ = (
        UniqueConstraint("blueprint_id", "anchor_key", name="uq_novel_blueprint_anchor_key"),
        Index("ix_novel_blueprint_anchor_kind", "blueprint_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    blueprint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("novel_blueprints.id", ondelete="CASCADE"), nullable=False
    )
    anchor_key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class NovelStructureCandidateModel(Base):
    __tablename__ = "novel_structure_candidates"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_novel_structure_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_volumes: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    impact: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=NovelCandidateStatus.ACTIVE)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class NovelDocumentRevisionModel(Base):
    __tablename__ = "novel_document_revisions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "chapter_id", "revision_number", name="uq_novel_chapter_revision"
        ),
        UniqueConstraint("project_id", "idempotency_key", name="uq_novel_document_request"),
        Index("ix_novel_document_chapter_status", "project_id", "chapter_id", "status"),
        Index(
            "uq_novel_document_one_adopted",
            "project_id",
            "chapter_id",
            unique=True,
            sqlite_where=text("status = 'adopted'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[str] = mapped_column(String(120), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    base_revision_id: Mapped[str | None] = mapped_column(String(36))
    parent_revision_id: Mapped[str | None] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(24), default="agent", nullable=False)
    blocks: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=NovelRevisionStatus.CANDIDATE)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class NovelQualityReportModel(Base):
    """Version-bound maturity assessment for one Novel chapter revision."""

    __tablename__ = "novel_quality_reports"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_novel_quality_request"),
        Index(
            "ix_novel_quality_revision",
            "project_id",
            "chapter_id",
            "revision_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[str] = mapped_column(String(120), nullable=False)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("novel_document_revisions.id", ondelete="CASCADE"), nullable=False
    )
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_profile_version: Mapped[str | None] = mapped_column(String(120))
    skill_plan_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    overall_status: Mapped[str] = mapped_column(String(24), nullable=False)
    maturity_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NovelSnapshotContentModel(Base):
    __tablename__ = "novel_snapshot_contents"

    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    documents: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class NovelExportManifestModel(Base):
    __tablename__ = "novel_export_manifests"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_novel_export_request"),
        Index("ix_novel_exports_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    form: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
