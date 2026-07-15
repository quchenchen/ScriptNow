"""Character — a Living Asset (see ADR-0002).

⚠ Many fields below are declared but not yet used by any UI or agent path.
Issue #07 (character-liveness) surfaces them.
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text

from .base import Base


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), default="supporting")  # protagonist / antagonist / supporting
    traits = Column(Text, default="")
    arc = Column(Text, default="")
    age = Column(String(20), default="")
    gender = Column(String(20), default="")
    personality = Column(Text, default="")
    background = Column(Text, default="")
    appearance = Column(Text, default="")
    current_state = Column(Text, default="")
    state_episode = Column(Integer, default=0)
    is_organization = Column(Integer, default=0)  # bool
    org_type = Column(String(100), default="")
    org_purpose = Column(String(500), default="")
    org_members = Column(Text, default="")
    career_id = Column(Integer, nullable=True)
    career_stage = Column(Integer, default=1)
    status = Column(String(20), default="active")  # active / suspended / deceased
    status_episode = Column(Integer, default=0)
    first_appearance = Column(Integer, default=0)
    last_appearance = Column(Integer, default=0)
