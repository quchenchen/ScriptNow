"""Project model.

A project is one artistic work being grown (see ADR-0001).
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
