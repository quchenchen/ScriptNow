"""Seed an admin user into the users table.

Idempotent: does nothing if the admin already exists.

Usage::

    python -m scripts.seed_admin

Runs synchronously via sqlite3 to avoid pulling the full app stack.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

# Make ``app`` importable when running as ``python -m scripts.seed_admin``
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db import DB_PATH  # noqa: E402

ADMIN_PHONE = "admin"
ADMIN_NICKNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_TIER = "expert"
ADMIN_POINTS = 9999


def seed() -> str:
    """Insert the admin user if not present. Returns a status message."""
    if not DB_PATH.exists():
        return f"skipped: DB not initialized at {DB_PATH} (run alembic upgrade head first)"

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute("SELECT id FROM users WHERE phone = ?", (ADMIN_PHONE,))
        if cur.fetchone():
            return "already-seeded"

        salt = secrets.token_hex(16)
        pwd_hash = hashlib.sha256(f"{salt}:{ADMIN_PASSWORD}".encode()).hexdigest()
        conn.execute(
            "INSERT INTO users (phone, nickname, password_hash, membership_tier, points) "
            "VALUES (?, ?, ?, ?, ?)",
            (ADMIN_PHONE, ADMIN_NICKNAME, f"{salt}:{pwd_hash}", ADMIN_TIER, ADMIN_POINTS),
        )
        conn.commit()
        return "seeded"
    finally:
        conn.close()


if __name__ == "__main__":
    print(seed())
