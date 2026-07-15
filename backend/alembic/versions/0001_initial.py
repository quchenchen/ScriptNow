"""initial schema — mirrors main.py's legacy CREATE TABLE.

Revision ID: 0001
Revises:
Create Date: 2026-07-15

This is a hand-written first migration corresponding to the schema previously
maintained as raw SQL inside ``app.main.init_db``. Every field name and type
matches the pre-V5 production schema to avoid data breakage on existing dev
databases.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(20), unique=True, nullable=False),
        sa.Column("nickname", sa.String(50), server_default=""),
        sa.Column("password_hash", sa.String(200), server_default=""),
        sa.Column("membership_tier", sa.String(20), server_default="free"),
        sa.Column("membership_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("points", sa.Integer, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("type", sa.String(20), server_default="script"),
        sa.Column("genre", sa.Text, server_default="[]"),
        sa.Column("target_audience", sa.String(50), server_default=""),
        sa.Column("cultural_background", sa.String(50), server_default="国内"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("current_stage", sa.String(20), server_default="ideation"),
        sa.Column("total_episodes", sa.Integer, server_default="80"),
        sa.Column("style_preference", sa.String(100), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "script_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("content", sa.Text, server_default="{}"),
        sa.Column("agent_name", sa.String(50), server_default=""),
        sa.Column("review_score", sa.Float, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version_id", sa.Integer, nullable=True),
        sa.Column("episode_number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), server_default=""),
        sa.Column("scenes", sa.Text, server_default="[]"),
        sa.Column("word_count", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("review_score", sa.Float, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("episode_id", sa.Integer, nullable=True),
        sa.Column("overall_score", sa.Float, server_default="0"),
        sa.Column("dimensions", sa.Text, server_default="{}"),
        sa.Column("issues", sa.Text, server_default="[]"),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), server_default="supporting"),
        sa.Column("traits", sa.Text, server_default=""),
        sa.Column("arc", sa.Text, server_default=""),
        sa.Column("age", sa.String(20), server_default=""),
        sa.Column("gender", sa.String(20), server_default=""),
        sa.Column("personality", sa.Text, server_default=""),
        sa.Column("background", sa.Text, server_default=""),
        sa.Column("appearance", sa.Text, server_default=""),
        sa.Column("current_state", sa.Text, server_default=""),
        sa.Column("state_episode", sa.Integer, server_default="0"),
        sa.Column("is_organization", sa.Integer, server_default="0"),
        sa.Column("org_type", sa.String(100), server_default=""),
        sa.Column("org_purpose", sa.String(500), server_default=""),
        sa.Column("org_members", sa.Text, server_default=""),
        sa.Column("career_id", sa.Integer, nullable=True),
        sa.Column("career_stage", sa.Integer, server_default="1"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("status_episode", sa.Integer, server_default="0"),
        sa.Column("first_appearance", sa.Integer, server_default="0"),
        sa.Column("last_appearance", sa.Integer, server_default="0"),
    )

    op.create_table(
        "foreshadows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("hint_text", sa.Text, server_default=""),
        sa.Column("resolution_text", sa.Text, server_default=""),
        sa.Column("category", sa.String(20), server_default="mystery"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("importance", sa.Float, server_default="0.5"),
        sa.Column("strength", sa.Integer, server_default="5"),
        sa.Column("subtlety", sa.Integer, server_default="5"),
        sa.Column("urgency", sa.Integer, server_default="0"),
        sa.Column("is_long_term", sa.Integer, server_default="0"),
        sa.Column("plant_episode", sa.Integer, nullable=True),
        sa.Column("target_episode", sa.Integer, nullable=True),
        sa.Column("actual_episode", sa.Integer, nullable=True),
        sa.Column("remind_before", sa.Integer, server_default="5"),
        sa.Column("auto_remind", sa.Integer, server_default="1"),
        sa.Column("include_context", sa.Integer, server_default="1"),
        sa.Column("related_characters", sa.Text, server_default="[]"),
        sa.Column("related_foreshadow_ids", sa.Text, server_default="[]"),
        sa.Column("tags", sa.Text, server_default="[]"),
    )

    op.create_table(
        "scene_assets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("asset_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("first_used", sa.Integer, server_default="0"),
        sa.Column("usage_count", sa.Integer, server_default="1"),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("agent_name", sa.String(50), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("scene_assets")
    op.drop_table("foreshadows")
    op.drop_table("characters")
    op.drop_table("reviews")
    op.drop_table("episodes")
    op.drop_table("script_versions")
    op.drop_table("projects")
    op.drop_table("users")
