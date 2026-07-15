"""pytest fixtures.

Rules of thumb (see AGENTS.md § 代码约定):
- Fixtures for setup, not assertions.
- Tests only touch public interfaces of the module under test.
- Use tmp_path / tmp_path_factory for anything that touches the filesystem.

Test isolation strategy:
- Every test gets a fresh env (isolate_env)
- Every test that boots the app gets a fresh DB (app_client evicts sys.modules
  cached ``app.*`` modules so ``DB_PATH`` re-resolves from the fresh env)
"""
from __future__ import annotations

import sys

import pytest


def _evict_app_modules() -> None:
    """Remove cached ``app.*`` modules so the next import re-resolves paths.

    Necessary because ``app.db.DB_PATH`` is computed at module-import time
    from the env var — later monkeypatch of the env has no effect on a
    module that's already been imported into ``sys.modules``.
    """
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


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
    # Force ``app.*`` modules to re-import against this test's env
    _evict_app_modules()
    yield
    # Also clean after the test to avoid leaking test state to the next module
    _evict_app_modules()


@pytest.fixture
def app_client(tmp_path):
    """FastAPI TestClient with the app booted up (lifespan run).

    Provided as a fixture so tests don't each have to boot the app.
    """
    from fastapi.testclient import TestClient

    # Late import to ensure env vars from _isolate_env are set AND the module
    # cache has been evicted by _isolate_env's autouse setup.
    from app.main import app

    with TestClient(app) as client:
        yield client
