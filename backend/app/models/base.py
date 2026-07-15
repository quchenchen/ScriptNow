"""Declarative base for all ORM models.

All SQLAlchemy models in this project inherit from ``Base`` defined here.
Import ``Base`` from ``app.models`` (the package re-exports it).
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""
