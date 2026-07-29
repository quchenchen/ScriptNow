from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_up_and_down(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "tenants",
        "sessions",
        "projects",
        "project_runs",
        "project_events",
        "token_usage",
        "credit_ledger",
        "memory_entries",
        "login_throttles",
        "script_story_maps",
        "novel_story_maps",
        "script_story_core_candidates",
        "script_blueprint_anchors",
        "script_document_revisions",
        "novel_story_core_candidates",
        "novel_blueprint_candidates",
        "novel_blueprints",
        "novel_blueprint_anchors",
        "novel_structure_candidates",
        "novel_document_revisions",
        "review_findings",
        "run_stream_events",
        "creative_context_manifests",
        "creative_retrieval_manifests",
        "creative_resumptions",
    } <= tables

    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
