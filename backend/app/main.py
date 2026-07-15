"""ScriptFlow Backend — FastAPI Application.

On startup we run Alembic migrations to bring the DB up to head, then seed
the default admin user (idempotent).

Historical: this module used to hold raw ``CREATE TABLE`` SQL alongside a
disjoint SQLAlchemy declaration. That's been consolidated:
- schema SoT lives in ``app.models`` (SQLAlchemy)
- migrations live in ``alembic/versions``
- DB session management lives in ``app.db``
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import ensure_db_dir


def _run_migrations() -> None:
    """Run Alembic upgrade head against the resolved DB path.

    We invoke alembic via its Python API rather than shelling out, so the
    process boundary stays inside FastAPI's lifespan.
    """
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    # env.py reads the URL from app.db; we just need cfg to point at the script location
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(cfg, "head")


def _seed_admin() -> None:
    """Best-effort seed of the default admin user.

    Never fails the boot on error — dev convenience only.
    """
    try:
        from scripts.seed_admin import seed
        seed()
    except Exception as e:  # pragma: no cover — dev convenience only
        import logging
        logging.getLogger(__name__).warning("admin seed skipped: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_db_dir()
    _run_migrations()
    _seed_admin()
    yield


app = FastAPI(title="ScriptFlow", lifespan=lifespan)

# CORS — permissive for dev. Issue #04 will tighten this for prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ScriptFlow"}


# Register routers
from app.api import (  # noqa: E402
    auth,
    llm_config,
    memory_api,
    projects,
    ralph,
    tree,
    workspace,
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
app.include_router(llm_config.router, prefix="/api/llm", tags=["llm"])
app.include_router(memory_api.router, prefix="/api/memory", tags=["memory"])
app.include_router(tree.router, prefix="/api/projects", tags=["tree"])
app.include_router(ralph.router, prefix="/api/projects", tags=["ralph"])
