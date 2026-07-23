from __future__ import annotations

import os

os.environ["SCRIPTFLOW_V6_DB_PATH"] = "/tmp/scriptflow-v6-test.db"

import pytest_asyncio

from scriptflow_v6.db import engine
from scriptflow_v6.models import Base


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
