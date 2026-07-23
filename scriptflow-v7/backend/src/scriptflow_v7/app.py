from contextlib import asynccontextmanager

from fastapi import FastAPI

from scriptflow_v7.dock.api import create_dock_router
from scriptflow_v7.novel.api import create_novel_router
from scriptflow_v7.novel.contracts import NOVEL_BLOCK_TYPES
from scriptflow_v7.novel.project import initialize_novel_project
from scriptflow_v7.platform.admin_api import create_admin_router
from scriptflow_v7.platform.auth import AuthService
from scriptflow_v7.platform.auth_api import create_auth_router
from scriptflow_v7.platform.config import Settings, get_settings
from scriptflow_v7.platform.core_api import create_core_router
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.narrative_graph_api import create_narrative_graph_router
from scriptflow_v7.review.api import create_review_router
from scriptflow_v7.script.api import create_script_router
from scriptflow_v7.script.contracts import SCRIPT_BLOCK_TYPES
from scriptflow_v7.script.project import initialize_script_project
from scriptflow_v7.work_package.api import create_work_package_router


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

    app = FastAPI(title="ScriptFlow V7", version="0.1.0", lifespan=lifespan)
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
    app.include_router(create_narrative_graph_router(resolved_database, auth, resolved_settings))
    app.include_router(create_review_router(resolved_database, auth))
    app.include_router(create_dock_router(resolved_database, auth, resolved_settings))
    app.include_router(create_work_package_router(resolved_database, auth, resolved_settings))

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
