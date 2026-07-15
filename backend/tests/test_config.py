"""Tests for the pydantic-settings-based config.

Guarantees:
- ``JWT_SECRET`` unset → refuse to boot (no silent random fallback that
  invalidates all tokens on every restart).
"""
from __future__ import annotations

import pytest


def test_settings_reads_jwt_secret_from_env(monkeypatch):
    """Given JWT_SECRET is set, Settings loads it."""
    monkeypatch.setenv("JWT_SECRET", "s" * 32)

    # Import late so env is picked up
    from app.config import Settings

    s = Settings()
    assert s.JWT_SECRET == "s" * 32


def test_settings_rejects_missing_jwt_secret(monkeypatch):
    """Given JWT_SECRET is missing, Settings() raises so the app refuses to boot."""
    monkeypatch.delenv("JWT_SECRET", raising=False)

    from app.config import Settings

    with pytest.raises(Exception) as excinfo:
        Settings()
    # pydantic v2 ValidationError message includes the missing field name
    assert "JWT_SECRET" in str(excinfo.value)


def test_settings_get_settings_is_cached(monkeypatch):
    """get_settings() memoizes the Settings instance."""
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    from app.config import get_settings

    a = get_settings()
    b = get_settings()
    assert a is b
