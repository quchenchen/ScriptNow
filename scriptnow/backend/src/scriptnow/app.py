from contextlib import asynccontextmanager

from fastapi import FastAPI

from scriptnow.dock.api import create_dock_router
from scriptnow.novel.api import create_novel_router
from scriptnow.novel.contracts import NOVEL_BLOCK_TYPES
from scriptnow.novel.cross_cultural_recreation.api import (
    create_cross_cultural_recreation_router,
)
from scriptnow.novel.project import initialize_novel_project
from scriptnow.platform.admin_api import create_admin_router
from scriptnow.platform.auth import AuthService
from scriptnow.platform.auth_api import create_auth_router
from scriptnow.platform.config import Settings, get_settings
from scriptnow.platform.core_api import create_core_router
from scriptnow.platform.database import Database
from scriptnow.platform.narrative_graph_api import create_narrative_graph_router
from scriptnow.review.api import create_review_router
from scriptnow.script.api import create_script_router
from scriptnow.script.contracts import SCRIPT_BLOCK_TYPES
from scriptnow.script.project import initialize_script_project
from scriptnow.translation.api import create_translation_router
from scriptnow.work_package.api import create_work_package_router


def create_app(
    *,
    database: Database | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_database = database or Database.create(resolved_settings.database_url)
    owns_database = database is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        del app
        yield
        if owns_database:
            await resolved_database.dispose()

    app = FastAPI(title="ScriptNow", version="0.1.0", lifespan=lifespan)
    app.state.database = resolved_database
    app.state.settings = resolved_settings
    auth = AuthService(resolved_database, resolved_settings)
    app.include_router(create_auth_router(auth, resolved_settings))
    app.include_router(create_admin_router(resolved_database, auth, resolved_settings))

    async def initialize_project(session, project):
        if project.medium == "script":
            await initialize_script_project(session, project)
        else:
            await initialize_novel_project(session, project)

    app.include_router(
        create_core_router(resolved_database, auth, resolved_settings, initialize_project)
    )
    app.include_router(create_script_router(resolved_database, auth, resolved_settings))
    app.include_router(create_novel_router(resolved_database, auth, resolved_settings))
    app.include_router(
        create_cross_cultural_recreation_router(
            resolved_database, auth, resolved_settings
        )
    )
    app.include_router(create_narrative_graph_router(resolved_database, auth, resolved_settings))
    app.include_router(create_review_router(resolved_database, auth))
    app.include_router(create_dock_router(resolved_database, auth, resolved_settings))
    app.include_router(create_work_package_router(resolved_database, auth, resolved_settings))
    app.include_router(create_translation_router(resolved_database, auth, resolved_settings))

    import os as _os

    from fastapi.staticfiles import StaticFiles

    covers_dir = _os.path.join(resolved_settings.workspace_root, "covers")
    _os.makedirs(covers_dir, exist_ok=True)
    app.mount("/files/covers", StaticFiles(directory=covers_dir), name="cover_files")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "domains": {
                "script": sorted(SCRIPT_BLOCK_TYPES),
                "novel": sorted(NOVEL_BLOCK_TYPES),
            },
        }

    return app


app = create_app()
