"""SceneAsset — legacy asset tracking (character/prop/location).

Will be superseded by dedicated ``scenes`` + ``props`` + ``visual_assets`` tables
(see ADR-0002 and issues #06, #08, and Phase 4 VisualAsset). Kept during
migration.
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text

from .base import Base


class SceneAsset(Base):
    __tablename__ = "scene_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    asset_type = Column(String(20), nullable=False)  # character/prop/location
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    first_used = Column(Integer, default=0)
    usage_count = Column(Integer, default=1)
