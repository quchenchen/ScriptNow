"""ScriptVersion — a snapshot of a stage's output for a given project.

Legacy structure. Will be superseded by Growth Tree nodes (issue #10).
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class ScriptVersion(Base):
    __tablename__ = "script_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    stage = Column(String(50), nullable=False)
    version = Column(Integer, default=1)
    content = Column(Text, default="{}")
    agent_name = Column(String(50), default="")
    review_score = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
