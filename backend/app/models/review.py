"""Review — output of a single Ralph Loop iteration (see ADR-0003 Tier 1).

Currently unwired. Issue #09 (ralph-loop-alive) writes here on every iteration.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.sql import func

from .base import Base


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    episode_id = Column(Integer, nullable=True)
    overall_score = Column(Float, default=0)
    dimensions = Column(Text, default="{}")  # JSON: {人物, 情节, 对白, 节奏, 钩子, 类型契合度}
    issues = Column(Text, default="[]")  # JSON list of {severity, description, suggestion}
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
