"""Tests for the Alembic-based schema management.

Verifies:
- ``alembic upgrade head`` creates every table the app expects
- ``alembic downgrade base`` reverses the schema cleanly
- The DB the app resolves matches the migration target

These tests use the ``tmp_path`` DB isolation from conftest, so nothing touches
the developer's real DB.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _run_upgrade_head() -> Path:
    """Run ``alembic upgrade head`` against the currently-configured DB path."""
    from alembic import command
    from alembic.config import Config
    from app.db import DB_PATH, ensure_db_dir

    ensure_db_dir()
    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(cfg, "head")
    return DB_PATH


def _run_downgrade_base() -> None:
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.downgrade(cfg, "base")


EXPECTED_TABLES = {
    "users",
    "projects",
    "script_versions",
    "episodes",
    "reviews",
    "characters",
    "foreshadows",
    "scene_assets",
    "chat_messages",
    "alembic_version",  # Alembic's own tracking table
}


def _list_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def test_upgrade_head_creates_all_expected_tables():
    """``alembic upgrade head`` yields every table the app expects."""
    db_path = _run_upgrade_head()

    tables = _list_tables(db_path)
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables after upgrade: {missing}"


def test_downgrade_base_removes_domain_tables():
    """``alembic downgrade base`` cleans up the domain tables."""
    db_path = _run_upgrade_head()
    _run_downgrade_base()

    tables = _list_tables(db_path)
    domain_tables = EXPECTED_TABLES - {"alembic_version"}
    remaining = tables & domain_tables
    assert not remaining, f"tables remained after downgrade: {remaining}"


def test_initial_revision_id_is_stable():
    """The initial migration keeps a stable revision id so downstream migrations
    can reference it. Changing this breaks anyone with an existing DB."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))

    scripts = ScriptDirectory.from_config(cfg)
    base_revisions = [r.revision for r in scripts.walk_revisions() if r.down_revision is None]
    assert base_revisions == ["0001"], (
        f"expected initial revision to be '0001', got {base_revisions}"
    )
