import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from scriptnow.dock.api import create_dock_router
from scriptnow.novel.api import create_novel_router
from scriptnow.novel.contracts import NOVEL_BLOCK_TYPES
from scriptnow.novel.cross_cultural_recreation.api import (
    create_cross_cultural_recreation_router,
)
from scriptnow.novel.project import initialize_novel_project
from scriptnow.platform.active_runs import ActiveRunRegistry
from scriptnow.platform.admin_api import create_admin_router
from scriptnow.platform.auth import AuthService
from scriptnow.platform.auth_api import create_auth_router
from scriptnow.platform.config import Settings, get_settings
from scriptnow.platform.core_api import create_core_router
from scriptnow.platform.database import Database
from scriptnow.platform.error_utils import user_facing_exception_message
from scriptnow.platform.narrative_graph_api import create_narrative_graph_router
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType
from scriptnow.review.api import create_review_router
from scriptnow.review.workbench_api import create_review_workbench_router
from scriptnow.script.api import create_script_router
from scriptnow.script.contracts import SCRIPT_BLOCK_TYPES
from scriptnow.script.project import initialize_script_project
from scriptnow.translation.api import create_translation_router
from scriptnow.work_package.api import create_work_package_router

from . import __version__


def create_app(
    *,
    database: Database | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_database = database or Database.create(resolved_settings.database_url)
    owns_database = database is None
    active_runs = ActiveRunRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        del app
        interrupted = await RunCoordinator(resolved_database).reconcile_interrupted()
        run_events = PersistentRunEventLog(resolved_database)
        for assessment in interrupted:
            run = assessment.run
            await run_events.append(
                tenant_id=run.tenant_id,
                run_id=run.id,
                event_key="runtime:interrupted",
                type=RunEventType.TERMINAL,
                payload={
                    "status": "failed",
                    "error_code": "runtime_interrupted",
                    "retryable": True,
                },
                correlation_id=run.id,
            )
        yield
        await active_runs.cancel_all()
        if owns_database:
            await resolved_database.dispose()

    app = FastAPI(title="ScriptNow", version=__version__, lifespan=lifespan)

    logger = logging.getLogger("scriptnow.api")

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        del request
        detail = user_facing_exception_message(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        detail = user_facing_exception_message(exc.errors())
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        error_id = str(uuid4())
        logger.exception(
            "Unhandled request failure [request_id=%s] for %s",
            error_id,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "internal server error",
                "error_id": error_id,
            },
        )

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response

    app.state.database = resolved_database
    app.state.settings = resolved_settings
    app.state.active_runs = active_runs
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
    app.include_router(
        create_script_router(resolved_database, auth, resolved_settings, active_runs)
    )
    app.include_router(
        create_novel_router(resolved_database, auth, resolved_settings, active_runs)
    )
    app.include_router(
        create_cross_cultural_recreation_router(
            resolved_database,
            auth,
            resolved_settings,
            active_runs,
        )
    )
    app.include_router(create_narrative_graph_router(resolved_database, auth, resolved_settings))
    app.include_router(create_review_router(resolved_database, auth, resolved_settings))
    app.include_router(
        create_review_workbench_router(resolved_database, auth, resolved_settings)
    )
    app.include_router(
        create_dock_router(resolved_database, auth, resolved_settings, active_runs)
    )
    app.include_router(create_work_package_router(resolved_database, auth, resolved_settings))
    app.include_router(
        create_translation_router(
            resolved_database,
            auth,
            resolved_settings,
            active_runs,
        )
    )

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
