from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from scriptnow.platform.database import Database
from scriptnow.platform.models import RefreshTokenModel, SessionModel, TenantModel, UserModel


@pytest.fixture
async def database() -> Database:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    yield database
    await database.dispose()


@pytest.mark.asyncio
async def test_database_session_commits_tenant_user_and_session(database: Database) -> None:
    async with database.session() as session:
        tenant = TenantModel(name="Studio A")
        session.add(tenant)
        await session.flush()
        user = UserModel(tenant_id=tenant.id, email="owner@example.com", password_hash="hash")
        session.add(user)
        await session.flush()
        session.add(
            session_record := SessionModel(
                tenant_id=tenant.id,
                user_id=user.id,
                csrf_token_hash="b" * 64,
                expires_at=datetime.now(UTC) + timedelta(days=30),
            ),
        )
        await session.flush()
        session.add(
            RefreshTokenModel(
                session_id=session_record.id,
                token_hash="a" * 64,
                expires_at=session_record.expires_at,
            ),
        )

    async with database.session() as session:
        stored = (await session.scalars(select(UserModel))).one()
        assert stored.email == "owner@example.com"
        assert stored.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_foreign_key_rejects_user_for_missing_tenant(database: Database) -> None:
    with pytest.raises(IntegrityError):
        async with database.session() as session:
            session.add(
                UserModel(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    email="orphan@example.com",
                    password_hash="hash",
                ),
            )


@pytest.mark.asyncio
async def test_transaction_rolls_back_all_changes_on_error(database: Database) -> None:
    with pytest.raises(RuntimeError):
        async with database.session() as session:
            session.add(TenantModel(name="Must rollback"))
            raise RuntimeError("stop")

    async with database.session() as session:
        assert list(await session.scalars(select(TenantModel))) == []
