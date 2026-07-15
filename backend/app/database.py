"""Backward-compat shim for legacy code that imports ``app.database``.

New code should import from ``app.db`` directly. This shim will be removed
when all API handlers migrate off aiosqlite (independent refactor).
"""
from __future__ import annotations

from app.db import (
    ASYNC_URL,
    DATABASE_URL,
    DB_PATH,
    async_session,
    engine,
    ensure_db_dir,
    get_aiosqlite_connection,
    get_sa_session,
)

__all__ = [
    "ASYNC_URL",
    "DATABASE_URL",
    "DB_PATH",
    "ensure_db_dir",
    "async_session",
    "engine",
    "get_aiosqlite_connection",
    "get_sa_session",
]
