from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scriptflow_v7.platform.database import Base
from scriptflow_v7.platform.models import new_id


class FindingDomain(StrEnum):
    WORLDVIEW = "worldview"
    CHARACTER = "character"
    ARC = "arc"
    EVENT = "event"
    FORESHADOW = "foreshadow"


class FindingSeverity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


class FindingSource(StrEnum):
    AI = "ai"
    HUMAN = "human"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    STALE = "stale"


class FindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: FindingDomain
    severity: FindingSeverity
    anchor_type: str
    anchor_id: str
    anchor_note: str = ""
    element_id: str
    original_excerpt: str = Field(min_length=2)
    locator: dict[str, object] = Field(default_factory=dict)
    diagnosis: str = Field(min_length=2)
    suggestion: str = Field(min_length=2)
    suggested_patch: dict[str, object]
    confidence: str = Field(pattern="^(high|mid|low)$")


class ReviewFindingModel(Base):
    __tablename__ = "review_findings"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_review_finding_request"),
        Index("ix_review_findings_filter", "project_id", "status", "severity", "domain"),
        Index("ix_review_findings_unit", "project_id", "unit_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    medium: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(120), nullable=False)
    base_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    element_id: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    anchor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    anchor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    anchor_note: Mapped[str] = mapped_column(String, default="")
    original_excerpt: Mapped[str] = mapped_column(String, nullable=False)
    locator: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    diagnosis: Mapped[str] = mapped_column(String, nullable=False)
    suggestion: Mapped[str] = mapped_column(String, nullable=False)
    suggested_patch: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=FindingStatus.OPEN)
    stale_reason: Mapped[str | None] = mapped_column(String)
    superseded_by: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
