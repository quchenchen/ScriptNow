"""Project model.

A project is one artistic work being grown (see ADR-0001).
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    type = Column(String(20), default="script")
    genre = Column(Text, default="[]")  # JSON string
    target_audience = Column(String(50), default="")
    cultural_background = Column(String(50), default="国内")
    status = Column(String(20), default="draft")
    current_stage = Column(String(20), default="ideation")
    total_episodes = Column(Integer, default=80)
    style_preference = Column(String(100), default="")
    # Ralph loop tuning (issue #09)
    ralph_pass_threshold = Column(Float, default=85.0)
    ralph_revise_threshold = Column(Float, default=60.0)
    ralph_max_retries = Column(Integer, default=3)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
