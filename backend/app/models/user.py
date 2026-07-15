"""User model.

Terminology: see CONTEXT.md § 术语速查表.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from .base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), unique=True, nullable=False)
    nickname = Column(String(50), default="")
    password_hash = Column(String(200), default="")
    membership_tier = Column(String(20), default="free")
    membership_expires = Column(DateTime(timezone=True), nullable=True)
    points = Column(Integer, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
