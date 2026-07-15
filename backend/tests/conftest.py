"""pytest fixtures.

Rules of thumb (see AGENTS.md § 代码约定):
- Fixtures for setup, not assertions.
- Tests only touch public interfaces of the module under test.
- Use tmp_path / tmp_path_factory for anything that touches the filesystem.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Every test starts with a clean env — no accidental leakage from the
    developer's real .env into unit tests.

    Provides a stable JWT_SECRET and a tmpdir-based DB path.
    """
    monkeypatch.setenv("JWT_SECRET", "test-secret-32-bytes-of-random-abcdefghijklmn")
    monkeypatch.setenv("SCRIPTFLOW_DB_PATH", str(tmp_path / "test.db"))
    # Ensure no real LLM calls during unit tests unless a test explicitly opts in
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


@pytest.fixture
def app_client(tmp_path):
    """FastAPI TestClient with the app booted up (lifespan run).

    Provided as a fixture so tests don't each have to boot the app.
    """
    from fastapi.testclient import TestClient

    # Late import to ensure env vars from _isolate_env are set
    from app.main import app

    with TestClient(app) as client:
        yield client
