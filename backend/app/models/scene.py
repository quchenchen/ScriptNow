"""Scene — a first-class entity, one row per script scene (see ADR-0002).

Historical: was ``episodes.scenes`` JSON. Issue #06 promotes it to its own
table so scenes can be queried, edited, and cross-referenced independently.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(Integer, ForeignKey("episodes.id"), nullable=False)
    scene_number = Column(Integer, nullable=False)  # 1-based, dense per-episode
    location = Column(String(200), default="")
    time = Column(String(100), default="")
    content = Column(Text, default="")
    characters_involved = Column(Text, default="[]")  # JSON — filled in by #07
    props_used = Column(Text, default="[]")  # JSON — filled in by #08
    status = Column(String(20), default="final")  # draft | final
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
