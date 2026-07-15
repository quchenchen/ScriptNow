"""Database session management — single source of truth.

Both aiosqlite (legacy code paths) and SQLAlchemy async (new code paths) resolve
the DB location the same way here. In lifespan we run Alembic migrations to
build/upgrade the schema.

Env vars:
- ``SCRIPTFLOW_DB_PATH`` — override the DB file location (default: ``data/scriptflow.db``
  relative to this backend/ directory).
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _resolve_db_path() -> Path:
    """Resolve the DB file path from env or default.

    We resolve at import time; tests use monkeypatch on ``SCRIPTFLOW_DB_PATH``
    before importing this module (see ``tests/conftest.py``).
    """
    override = os.getenv("SCRIPTFLOW_DB_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return _BACKEND_ROOT / "data" / "scriptflow.db"


DB_PATH: Path = _resolve_db_path()
ASYNC_URL = f"sqlite+aiosqlite:///{DB_PATH}"
SYNC_URL = f"sqlite:///{DB_PATH}"  # used by alembic

# Legacy alias — some callers import ``DATABASE_URL`` from ``app.models``.
DATABASE_URL = ASYNC_URL


def ensure_db_dir() -> None:
    """Create the parent directory of the DB file if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# SQLAlchemy async engine (for new code paths)
engine = create_async_engine(ASYNC_URL, echo=False, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_sa_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Dependency yielding an AsyncSession."""
    async with async_session() as session:
        yield session


# ── aiosqlite helper for legacy code paths ────────────────────────────────

async def get_aiosqlite_connection() -> aiosqlite.Connection:
    """Return a raw aiosqlite connection with Row row_factory.

    Legacy API handlers (workspace.py, projects.py, etc.) still use this until
    they're migrated to SQLAlchemy in later slices.
    """
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    return conn
