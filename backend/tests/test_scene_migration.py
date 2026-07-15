"""Tests for the scenes-table migration (0002).

Each fixture seeds a pre-migration DB with old-shape ``episodes.scenes`` JSON,
runs ``alembic upgrade head``, then verifies the resulting ``scenes`` table.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _stamp_and_seed(db_path: Path, episodes_scenes_data: list[tuple[int, str]]):
    """Apply migration 0001 only, then seed episodes with legacy scenes JSON.

    ``episodes_scenes_data`` is a list of (episode_number, scenes_json_str).
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "0001")  # bring the DB up to just 0001

    # Seed
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO users (phone, nickname, password_hash) VALUES ('u1', 'alice', 'x:y')"
        )
        conn.execute(
            "INSERT INTO projects (user_id, title, type) VALUES (1, 'P1', 'script')"
        )
        for ep_num, scenes_json in episodes_scenes_data:
            conn.execute(
                "INSERT INTO episodes (project_id, episode_number, title, scenes, status) "
                "VALUES (1, ?, ?, ?, 'done')",
                (ep_num, f"第{ep_num}集", scenes_json),
            )
        conn.commit()
    finally:
        conn.close()


def _upgrade_head():
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _list_scenes(db_path: Path, episode_number: int) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT s.scene_number, s.location, s.time, s.content "
            "FROM scenes s JOIN episodes e ON s.episode_id = e.id "
            "WHERE e.episode_number = ? ORDER BY s.scene_number",
            (episode_number,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _episodes_scenes_column_gone(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(episodes)").fetchall()}
        return "scenes" not in cols
    finally:
        conn.close()


# ── Fixtures ─────────────────────────────────────────────────────────────

def test_migration_empty_project():
    """No episodes → migration succeeds, scenes table empty, column dropped."""
    from app.db import DB_PATH
    _stamp_and_seed(DB_PATH, episodes_scenes_data=[])
    _upgrade_head()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        count = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
    assert _episodes_scenes_column_gone(DB_PATH)


def test_migration_single_scene_no_markers():
    """Legacy shape ``[{"content": "..."}]`` with no ``【场景N】`` markers.

    Should become a single scene row with the whole text.
    """
    from app.db import DB_PATH
    legacy = json.dumps(
        [{"content": "阿明走进咖啡馆，看到了她。\n她转过头，笑了。"}], ensure_ascii=False
    )
    _stamp_and_seed(DB_PATH, [(1, legacy)])
    _upgrade_head()

    scenes = _list_scenes(DB_PATH, episode_number=1)
    assert len(scenes) == 1
    assert scenes[0]["scene_number"] == 1
    assert scenes[0]["location"] == ""
    assert "阿明" in scenes[0]["content"]


def test_migration_multi_scene_with_markers():
    """Legacy content with ``【场景N】location·time`` markers gets split correctly."""
    from app.db import DB_PATH
    content = (
        "【场景1】咖啡馆·白天\n"
        "△推门\n"
        "阿明：你终于来了。\n\n"
        "【场景2】街道·夜\n"
        "△下雨\n"
        "小红：走吧。"
    )
    legacy = json.dumps([{"content": content}], ensure_ascii=False)
    _stamp_and_seed(DB_PATH, [(1, legacy)])
    _upgrade_head()

    scenes = _list_scenes(DB_PATH, episode_number=1)
    assert len(scenes) == 2

    assert scenes[0]["scene_number"] == 1
    assert scenes[0]["location"] == "咖啡馆"
    assert scenes[0]["time"] == "白天"
    assert "推门" in scenes[0]["content"]
    assert "阿明：你终于来了" in scenes[0]["content"]

    assert scenes[1]["scene_number"] == 2
    assert scenes[1]["location"] == "街道"
    assert scenes[1]["time"] == "夜"
    assert "小红：走吧" in scenes[1]["content"]


def test_migration_corrupted_json_preserves_raw_text():
    """Corrupted legacy JSON should not lose data — dumped as a single raw scene."""
    from app.db import DB_PATH
    _stamp_and_seed(DB_PATH, [(1, "not valid json {{")])
    _upgrade_head()

    scenes = _list_scenes(DB_PATH, episode_number=1)
    assert len(scenes) == 1
    assert "not valid json" in scenes[0]["content"]


def test_migration_downgrade_round_trip():
    """Downgrade recreates the legacy shape from scene rows."""
    from alembic import command
    from alembic.config import Config
    from app.db import DB_PATH

    content = "【场景1】咖啡馆·白天\n阿明：你好。"
    legacy = json.dumps([{"content": content}], ensure_ascii=False)
    _stamp_and_seed(DB_PATH, [(1, legacy)])
    _upgrade_head()

    # Downgrade back to 0001
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.downgrade(cfg, "0001")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        # scenes table gone
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "scenes" not in tables
        # episodes.scenes column back
        cols = {r[1] for r in conn.execute("PRAGMA table_info(episodes)").fetchall()}
        assert "scenes" in cols
        # Content preserved
        row = conn.execute(
            "SELECT scenes FROM episodes WHERE episode_number = 1"
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert "咖啡馆" in payload[0]["content"]
    finally:
        conn.close()
