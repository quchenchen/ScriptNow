from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from scriptnow.platform.database import Base
from scriptnow.platform.models import new_id, utc_now


class RecreationStatus(StrEnum):
    SOURCE_PENDING = "source_pending"
    SOURCE_ANALYZED = "source_analyzed"
    TARGET_CONFIRMED = "target_confirmed"
    STRATEGY_READY = "strategy_ready"
    STRATEGY_ADOPTED = "strategy_adopted"
    PILOT_READY = "pilot_ready"
    PILOT_ADOPTED = "pilot_adopted"
    SCALE_PLAN_READY = "scale_plan_ready"
    SCALE_PLAN_ADOPTED = "scale_plan_adopted"
    PRODUCTION_IN_PROGRESS = "production_in_progress"
    PRODUCTION_COMPLETE = "production_complete"


class RecreationArtifactKind(StrEnum):
    SOURCE_STORY_MODEL = "source_story_model"
    TARGET_STORY_CONTRACT = "target_story_contract"
    RECREATION_STRATEGY = "recreation_strategy"
    CULTURAL_MAPPING_SET = "cultural_mapping_set"
    PROTECTION_CONFLICT_DECISION = "protection_conflict_decision"
    PILOT = "pilot"
    SCALE_PLAN = "scale_plan"


class RecreationArtifactStatus(StrEnum):
    CANDIDATE = "candidate"
    ADOPTED = "adopted"
    SUPERSEDED = "superseded"


class ChapterPipelineStatus(StrEnum):
    DRAFTING = "drafting"
    VALIDATING = "validating"
    REVIEW_PENDING = "review_pending"
    REVISION_REQUIRED = "revision_required"
    READY_FOR_DECISION = "ready_for_decision"
    ADOPTED = "adopted"
    FAILED = "failed"


class ChapterRevisionKind(StrEnum):
    AGENT = "agent"
    MANUAL = "manual"


class RecreationProductionUnitModel(Base):
    __tablename__ = "cross_cultural_production_units"
    __table_args__ = (
        UniqueConstraint(
            "recreation_id",
            "scale_plan_artifact_id",
            "work_package_key",
            "version",
            name="uq_cross_cultural_production_unit_version",
        ),
        UniqueConstraint(
            "recreation_id",
            "work_package_key",
            "idempotency_key",
            name="uq_cross_cultural_production_unit_request",
        ),
        Index(
            "uq_cross_cultural_one_adopted_production_unit",
            "recreation_id",
            "scale_plan_artifact_id",
            "work_package_key",
            unique=True,
            sqlite_where=text("status = 'adopted'"),
        ),
        Index(
            "ix_cross_cultural_production_unit_lookup",
            "recreation_id",
            "scale_plan_artifact_id",
            "work_package_key",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recreation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cross_cultural_recreations.id", ondelete="CASCADE"),
        nullable=False,
    )
    scale_plan_artifact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cross_cultural_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=RecreationArtifactStatus.CANDIDATE, nullable=False
    )
    pipeline_status: Mapped[str] = mapped_column(
        String(32), default=ChapterPipelineStatus.DRAFTING, nullable=False
    )
    revision_kind: Mapped[str] = mapped_column(
        String(16), default=ChapterRevisionKind.AGENT, nullable=False
    )
    source_unit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("cross_cultural_production_units.id", ondelete="SET NULL"),
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    context_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    review_report: Mapped[dict[str, object] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String)
    feedback: Mapped[str | None] = mapped_column(String)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CrossCulturalRecreationModel(Base):
    __tablename__ = "cross_cultural_recreations"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_cross_cultural_recreation_project"),
        Index("ix_cross_cultural_recreation_tenant", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_language: Mapped[str] = mapped_column(String(24), nullable=False)
    target_language: Mapped[str] = mapped_column(String(24), nullable=False)
    target_market: Mapped[str] = mapped_column(String(160), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(240), nullable=False)
    distribution_context: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(48), default=RecreationStatus.SOURCE_PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CrossCulturalArtifactModel(Base):
    __tablename__ = "cross_cultural_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "recreation_id",
            "kind",
            "version",
            "ordinal",
            name="uq_cross_cultural_artifact_version",
        ),
        UniqueConstraint(
            "recreation_id",
            "kind",
            "idempotency_key",
            "ordinal",
            name="uq_cross_cultural_artifact_request",
        ),
        Index(
            "uq_cross_cultural_one_adopted",
            "recreation_id",
            "kind",
            unique=True,
            sqlite_where=text("status = 'adopted'"),
        ),
        Index("ix_cross_cultural_artifact_lookup", "recreation_id", "kind", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recreation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cross_cultural_recreations.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=RecreationArtifactStatus.CANDIDATE, nullable=False
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    feedback: Mapped[str | None] = mapped_column(String)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
