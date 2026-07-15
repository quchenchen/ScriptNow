"""ORM models for ScriptFlow.

Import ``Base`` here so Alembic autogenerate sees all tables. Every new model
file must be imported below.

Also exports ``DATABASE_URL`` for legacy code that imports it from
``app.models`` directly. New code should use ``app.db.ASYNC_URL`` instead.
"""
from __future__ import annotations

from app.db import DATABASE_URL

from .base import Base
from .character import Character
from .chat_message import ChatMessage
from .episode import Episode
from .foreshadow import Foreshadow
from .growth_tree import GrowthEdge, GrowthNode
from .project import Project
from .review import Review
from .scene import Scene
from .scene_asset import SceneAsset
from .script_version import ScriptVersion
from .user import User

__all__ = [
    "Base",
    "DATABASE_URL",
    "Character",
    "ChatMessage",
    "Episode",
    "Foreshadow",
    "GrowthEdge",
    "GrowthNode",
    "Project",
    "Review",
    "Scene",
    "SceneAsset",
    "ScriptVersion",
    "User",
]
