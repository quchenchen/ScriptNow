from fastapi.testclient import TestClient

from scriptnow.app import create_app
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    RunStatus,
    TenantModel,
)


def test_health_exposes_both_isolated_domains() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "domains": {
            "script": ["action", "character", "dialogue", "slugline", "transition"],
            "novel": ["dialogue", "divider", "heading", "prose", "quote"],
        },
    }


def test_cross_cultural_recreation_uses_the_shared_api_proxy_contract() -> None:
    paths = TestClient(create_app()).app.openapi()["paths"]

    assert "/cross-cultural-recreations" in paths
    assert "/api/cross-cultural-recreations" not in paths


def test_standalone_review_api_is_not_nested_under_a_project() -> None:
    paths = TestClient(create_app()).app.openapi()["paths"]

    assert "/review-agent/cases" in paths
    assert "/review-agent/cases/{case_id}/messages" in paths
    assert not any(path.startswith("/projects/{project_id}/review-agent/cases") for path in paths)


def test_app_startup_reconciles_interrupted_runs_without_crashing(tmp_path) -> None:
    import asyncio

    database = Database.create(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")

    async def seed() -> None:
        await database.create_schema()
        async with database.session() as session:
            tenant = TenantModel(name="Studio", tier="plus")
            session.add(tenant)
            await session.flush()
            project = ProjectModel(
                tenant_id=tenant.id,
                name="图谱启动验证",
                medium=ProjectMedium.NOVEL,
                direction={"language": "zh-CN"},
            )
            session.add(project)
            await session.flush()
            session.add(
                ProjectRunModel(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    idempotency_key="interrupted-graph-run",
                    status=RunStatus.RUNNING,
                )
            )
            await session.flush()

    asyncio.run(seed())
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    app = create_app(database=database, settings=settings)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    asyncio.run(database.dispose())


def test_default_security_headers_present() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains; preload"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"
