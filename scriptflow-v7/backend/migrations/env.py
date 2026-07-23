import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from scriptflow_v7.novel import domain as novel_domain  # noqa: F401
from scriptflow_v7.novel import project as novel_project  # noqa: F401
from scriptflow_v7.platform import models  # noqa: F401
from scriptflow_v7.platform.database import Base
from scriptflow_v7.review import domain as review_domain  # noqa: F401
from scriptflow_v7.script import domain as script_domain  # noqa: F401
from scriptflow_v7.script import project as script_project  # noqa: F401

config = context.config
if migration_url := os.getenv("SCRIPTFLOW_V7_MIGRATION_URL"):
    config.set_main_option("sqlalchemy.url", migration_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    url = configuration.get("sqlalchemy.url", "")
    configuration["sqlalchemy.url"] = url.replace("+aiosqlite", "")
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
