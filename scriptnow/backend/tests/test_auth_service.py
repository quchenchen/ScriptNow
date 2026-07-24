from uuid import uuid4

import jwt
import pytest

from scriptnow.platform.auth import (
    AuthenticationFailed,
    AuthService,
    CsrfFailed,
    LoginRateLimited,
    PasswordHasher,
    RefreshTokenReuseDetected,
)
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database


@pytest.fixture
async def auth() -> tuple[AuthService, Database, Settings]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    settings = Settings(access_token_secret="test-secret-that-is-at-least-24-bytes")
    service = AuthService(database, settings)
    await service.create_tenant_owner(
        tenant_name="Studio A",
        email="owner@example.com",
        password="correct horse battery staple",
    )
    yield service, database, settings
    await database.dispose()


def test_password_hash_is_salted_and_rejects_short_password() -> None:
    hasher = PasswordHasher()
    first = hasher.hash("correct horse battery staple")
    second = hasher.hash("correct horse battery staple")

    assert first != second
    assert hasher.verify("correct horse battery staple", first)
    assert not hasher.verify("wrong password", first)
    with pytest.raises(ValueError, match="at least 12"):
        hasher.hash("short")


@pytest.mark.asyncio
async def test_login_access_refresh_rotation_and_logout(
    auth: tuple[AuthService, Database, Settings],
) -> None:
    service, _, settings = auth
    tokens = await service.login("OWNER@example.com", "correct horse battery staple")
    context = await service.validate_access(tokens.access_token)
    claims = jwt.decode(
        tokens.access_token,
        settings.access_token_secret,
        algorithms=["HS256"],
        audience=settings.creator_audience,
        issuer=settings.access_token_issuer,
    )

    assert str(context.tenant_id) == claims["tid"]
    rotated = await service.refresh(tokens.refresh_token, tokens.csrf_token)
    assert rotated.refresh_token != tokens.refresh_token
    await service.logout(rotated.access_token, rotated.csrf_token)
    with pytest.raises(AuthenticationFailed):
        await service.validate_access(rotated.access_token)


@pytest.mark.asyncio
async def test_refresh_requires_matching_csrf(auth: tuple[AuthService, Database, Settings]) -> None:
    service, _, _ = auth
    tokens = await service.login("owner@example.com", "correct horse battery staple")

    with pytest.raises(CsrfFailed):
        await service.refresh(tokens.refresh_token, "wrong-csrf")


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_whole_session(
    auth: tuple[AuthService, Database, Settings],
) -> None:
    service, _, _ = auth
    first = await service.login("owner@example.com", "correct horse battery staple")
    second = await service.refresh(first.refresh_token, first.csrf_token)

    with pytest.raises(RefreshTokenReuseDetected):
        await service.refresh(first.refresh_token, first.csrf_token)
    with pytest.raises(AuthenticationFailed):
        await service.validate_access(second.access_token)


@pytest.mark.asyncio
async def test_tampered_tenant_claim_is_rejected(
    auth: tuple[AuthService, Database, Settings],
) -> None:
    service, _, settings = auth
    tokens = await service.login("owner@example.com", "correct horse battery staple")
    claims = jwt.decode(
        tokens.access_token,
        settings.access_token_secret,
        algorithms=["HS256"],
        audience=settings.creator_audience,
        issuer=settings.access_token_issuer,
    )
    claims["tid"] = str(uuid4())
    forged = jwt.encode(claims, settings.access_token_secret, algorithm="HS256")

    with pytest.raises(AuthenticationFailed):
        await service.validate_access(forged)


@pytest.mark.asyncio
async def test_failed_logins_are_persistently_rate_limited() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    settings = Settings(
        access_token_secret="test-secret-that-is-at-least-24-bytes", login_max_failures=2
    )
    service = AuthService(database, settings)
    await service.create_tenant_owner(
        tenant_name="Studio",
        email="owner@example.com",
        password="correct horse battery staple",
    )
    for _ in range(2):
        with pytest.raises(AuthenticationFailed):
            await service.login(
                "owner@example.com", "wrong password long enough", client_key="198.51.100.1"
            )
    with pytest.raises(LoginRateLimited):
        await service.login(
            "owner@example.com", "correct horse battery staple", client_key="198.51.100.1"
        )
    assert await service.login(
        "owner@example.com", "correct horse battery staple", client_key="198.51.100.2"
    )
    await database.dispose()
