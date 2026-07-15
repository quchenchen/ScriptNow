"""Foreshadow — a Living Asset (see ADR-0002).

State machine: pending → planted → partially_resolved → resolved
                                              ↘ abandoned

Issue #08 (foreshadow-prop-boards) makes the state machine actually enforced.
"""
from __future__ import annotations

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text

from .base import Base


class Foreshadow(Base):
    __tablename__ = "foreshadows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    hint_text = Column(Text, default="")
    resolution_text = Column(Text, default="")
    category = Column(String(20), default="mystery")
    status = Column(String(20), default="pending")
    importance = Column(Float, default=0.5)
    strength = Column(Integer, default=5)
    subtlety = Column(Integer, default=5)
    urgency = Column(Integer, default=0)
    is_long_term = Column(Integer, default=0)
    plant_episode = Column(Integer, nullable=True)
    target_episode = Column(Integer, nullable=True)
    actual_episode = Column(Integer, nullable=True)
    remind_before = Column(Integer, default=5)
    auto_remind = Column(Integer, default=1)
    include_context = Column(Integer, default=1)
    related_characters = Column(Text, default="[]")  # JSON
    related_foreshadow_ids = Column(Text, default="[]")  # JSON
    tags = Column(Text, default="[]")  # JSON
