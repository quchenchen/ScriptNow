"""RalphIteration — one row per review round in the write→review→revise loop.

See ADR-0003 / issue #09. Column ``review_dimensions`` / ``review_issues`` are
JSON strings (list of dicts); parse at the boundary.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class RalphIteration(Base):
    __tablename__ = "ralph_iterations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(Integer, ForeignKey("episodes.id"), nullable=False)
    iteration = Column(Integer, nullable=False)  # 1-based per episode
    writing_output = Column(Text, default="")  # snapshot of what was reviewed
    review_score = Column(Float, default=0.0)
    review_dimensions = Column(Text, default="{}")  # JSON dict
    review_issues = Column(Text, default="[]")  # JSON list
    decision = Column(String(20), default="")  # pass|revise|restructure|escalate
    created_at = Column(DateTime(timezone=True), server_default=func.now())
