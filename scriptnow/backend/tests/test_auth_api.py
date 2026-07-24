import pytest
from httpx import ASGITransport, AsyncClient

from scriptnow.app import create_app
from scriptnow.platform.auth import AuthService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database


@pytest.fixture
async def client() -> AsyncClient:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    settings = Settings(access_token_secret="test-secret-that-is-at-least-24-bytes")
    await AuthService(database, settings).create_tenant_owner(
        tenant_name="Studio A",
        email="owner@example.com",
        password="correct horse battery staple",
    )
    app = create_app(database=database, settings=settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value
    await database.dispose()


@pytest.mark.asyncio
async def test_cookie_login_me_refresh_and_logout(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    assert client.cookies.get("sf_access")
    assert client.cookies.get("sf_refresh")
    csrf = client.cookies["sf_csrf"]
    assert (await client.get("/auth/me")).status_code == 200

    refreshed = await client.post("/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    rotated_csrf = client.cookies["sf_csrf"]
    assert rotated_csrf != csrf

    logout = await client.post("/auth/logout", headers={"X-CSRF-Token": rotated_csrf})
    assert logout.status_code == 204
    assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_refresh_and_logout_require_csrf(client: AsyncClient) -> None:
    await client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )

    assert (await client.post("/auth/refresh")).status_code == 403
    assert (await client.post("/auth/logout")).status_code == 403


@pytest.mark.asyncio
async def test_invalid_login_does_not_reveal_account_existence(client: AsyncClient) -> None:
    wrong_password = await client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "totally wrong password"},
    )
    missing_user = await client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "totally wrong password"},
    )

    assert wrong_password.status_code == missing_user.status_code == 401
    assert wrong_password.json() == missing_user.json()
