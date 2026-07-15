"""Episode model.

An episode is a written unit within a script.

⚠ Historical debt (see ADR-0002):
- ``scenes`` currently holds "the whole episode text as one JSON scene". Issue #06
  migrates that to an independent ``scenes`` table.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    version_id = Column(Integer, nullable=True)
    episode_number = Column(Integer, nullable=False)
    title = Column(String(200), default="")
    scenes = Column(Text, default="[]")  # JSON, historical (see class docstring)
    word_count = Column(Integer, default=0)
    status = Column(String(20), default="pending")
    review_score = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
