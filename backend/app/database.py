"""Database session management — dual-mode: aiosqlite (existing) + SQLAlchemy async (new)."""
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from pathlib import Path
from app.models import DATABASE_URL as _SA_URL

DB_PATH = Path(__file__).parent / "data" / "scriptflow.db"
ASYNC_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# SQLAlchemy async engine (for new code)
engine = create_async_engine(ASYNC_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# aiosqlite helper (for existing code, backward compat)
async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db

async def get_sa_session() -> AsyncSession:
    async with async_session() as session:
        yield session
