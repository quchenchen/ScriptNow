from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def database_url() -> str:
    path = os.getenv("SCRIPTFLOW_V6_DB_PATH", "./data/scriptflow-v6.db")
    return f"sqlite+aiosqlite:///{path}"


engine = create_async_engine(database_url())
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as value:
        yield value
