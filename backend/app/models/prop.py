"""Prop — a Living Asset for physical/logical objects that recur in scenes.

Contrast with :class:`SceneAsset` (legacy free-form asset tracking that will
be deprecated once Character/Foreshadow/Prop are all first-class).

``significance`` categorizes intent:
    background     — dressing / period-authentic detail
    plot_device    — object that drives a specific plot beat
    macguffin      — object whose meaning drives the story (Hitchcock's usage)
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class Prop(Base):
    __tablename__ = "props"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    significance = Column(String(20), default="background")  # background/plot_device/macguffin
    first_appearance = Column(Integer, default=0)  # episode number
    last_appearance = Column(Integer, default=0)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
