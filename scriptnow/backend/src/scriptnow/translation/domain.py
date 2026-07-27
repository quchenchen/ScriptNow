from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scriptnow.platform.database import Base


class TranslationSnapshotContentModel(Base):
    """Point-in-time translated documents; metadata lives in project_snapshots."""

    __tablename__ = "translation_snapshot_contents"

    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    documents: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class TranslationGlossaryTermModel(Base):
    __tablename__ = "translation_glossary_terms"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_term", name="uq_translation_glossary_source"
        ),
        Index("ix_translation_glossary_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_term: Mapped[str] = mapped_column(String(240), nullable=False)
    target_term: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="candidate", nullable=False)
    source: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)


class TranslationCorrectionModel(Base):
    """An explicit, user-controlled replacement required by a glossary change."""

    __tablename__ = "translation_corrections"
    __table_args__ = (
        Index("ix_translation_correction_project_status", "project_id", "status"),
        Index("ix_translation_correction_term_status", "term_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("translation_glossary_terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_id: Mapped[str] = mapped_column(String(120), nullable=False)
    previous_target: Mapped[str] = mapped_column(String(240), nullable=False)
    required_target: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
