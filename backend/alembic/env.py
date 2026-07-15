"""Alembic env.py.

Reads the DB URL from ``app.db`` at runtime rather than from alembic.ini, so
tests and dev/prod all share the same resolution logic (with
``SCRIPTFLOW_DB_PATH`` override respected).

The target metadata is ``app.models.Base.metadata`` — every model file must
be imported in ``app/models/__init__.py`` for autogenerate to detect them.
"""
from __future__ import annotations

# Ensure backend/ is on sys.path so `import app` works when running alembic CLI
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db import SYNC_URL, ensure_db_dir  # noqa: E402
from app.models import Base  # noqa: E402

# This is the Alembic Config object, which provides access to values from
# alembic.ini.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the URL from alembic.ini with the one resolved by app.db
config.set_main_option("sqlalchemy.url", SYNC_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout without connecting to a DB. Useful for generating
    migration scripts to review before running.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    ensure_db_dir()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
