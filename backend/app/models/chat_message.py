"""ChatMessage — persisted user↔agent conversation.

Used both for UI history replay and (later, issue #13) for Style Library
learning.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(String(10), nullable=False)  # user / agent
    content = Column(Text, nullable=False)
    agent_name = Column(String(50), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
