"""scenes table + data migration + drop episodes.scenes column.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15

Promotes ``episodes.scenes`` (JSON) to a dedicated ``scenes`` table
(one row per scene). See ADR-0002 and issue #06.

Data migration strategy:
- For each episode row with a non-empty ``scenes`` JSON:
  - Try to parse. On success, iterate the list.
  - For each item, extract its ``content`` (the historical shape was
    ``[{"content": "the whole episode text"}]``).
  - Split that content by ``【场景N】location·time`` markers into scenes.
  - If no markers found, treat the whole text as scene #1.
- Insert each scene as a row.
- Finally, drop ``episodes.scenes`` (batch mode for SQLite).

Downgrade:
- Recreate ``episodes.scenes`` column.
- Reassemble scene rows back to JSON per episode.
- Drop ``scenes`` table.
"""
from __future__ import annotations

import json
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Match a scene heading line: ``【场景1】location·time`` (location and time
# both optional). Line-based analysis is more readable than a single mega
# regex and handles edge cases (empty location, no time separator) cleanly.
_HEAD_RE = re.compile(r"^\s*【场景\s*(\d+)\s*】\s*(.*)$")


def _split_content_into_scenes(content: str) -> list[dict]:
    """Split raw episode text into scene dicts by ``【场景N】`` markers.

    Returns ``[{"scene_number", "location", "time", "content"}, ...]``.
    If no markers found, the whole content becomes scene #1.
    """
    if not content:
        return []

    current: dict | None = None
    scenes: list[dict] = []

    for line in content.split("\n"):
        m = _HEAD_RE.match(line)
        if m:
            if current is not None:
                scenes.append(current)
            rest = (m.group(2) or "").strip()
            if "·" in rest:
                loc, t = rest.split("·", 1)
                loc, t = loc.strip(), t.strip()
            else:
                loc, t = rest, ""
            current = {"location": loc, "time": t, "content_lines": []}
        else:
            if current is None:
                # Content before any ``【场景N】`` marker — start scene 1 implicitly
                current = {"location": "", "time": "", "content_lines": [line]}
            else:
                current["content_lines"].append(line)

    if current is not None:
        scenes.append(current)

    if not scenes:
        return [{"scene_number": 1, "location": "", "time": "", "content": content.strip()}]

    return [
        {
            "scene_number": i,  # renumber densely
            "location": s["location"],
            "time": s["time"],
            "content": "\n".join(s["content_lines"]).strip(),
        }
        for i, s in enumerate(scenes, start=1)
    ]


def upgrade() -> None:
    # 1. Create scenes table
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("episode_id", sa.Integer, sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("scene_number", sa.Integer, nullable=False),
        sa.Column("location", sa.String(200), server_default=""),
        sa.Column("time", sa.String(100), server_default=""),
        sa.Column("content", sa.Text, server_default=""),
        sa.Column("characters_involved", sa.Text, server_default="[]"),
        sa.Column("props_used", sa.Text, server_default="[]"),
        sa.Column("status", sa.String(20), server_default="final"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Data migration: read each episode's scenes JSON, split, insert into scenes table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("episodes")}
    if "scenes" in columns:
        rows = bind.execute(sa.text("SELECT id, scenes FROM episodes")).fetchall()
        for ep_id, scenes_json in rows:
            if not scenes_json:
                continue
            try:
                items = json.loads(scenes_json)
            except json.JSONDecodeError:
                # Corrupted JSON — preserve raw text as one scene so we don't lose data
                bind.execute(
                    sa.text(
                        "INSERT INTO scenes (episode_id, scene_number, content) "
                        "VALUES (:ep, 1, :c)"
                    ),
                    {"ep": ep_id, "c": scenes_json},
                )
                continue

            if not isinstance(items, list) or not items:
                continue

            # Collect all content from all items, then split
            merged = "\n\n".join((it.get("content") or "") for it in items if isinstance(it, dict))
            scenes = _split_content_into_scenes(merged)
            for s in scenes:
                bind.execute(
                    sa.text(
                        "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
                        "VALUES (:ep, :n, :loc, :t, :c)"
                    ),
                    {"ep": ep_id, "n": s["scene_number"], "loc": s["location"],
                     "t": s["time"], "c": s["content"]},
                )

        # 3. Drop the legacy column (SQLite batch mode)
        with op.batch_alter_table("episodes") as batch:
            batch.drop_column("scenes")


def downgrade() -> None:
    # 1. Re-add episodes.scenes column
    with op.batch_alter_table("episodes") as batch:
        batch.add_column(sa.Column("scenes", sa.Text, server_default="[]"))

    # 2. Reassemble scenes JSON per episode
    bind = op.get_bind()
    ep_ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM episodes")).fetchall()]
    for ep_id in ep_ids:
        rows = bind.execute(
            sa.text(
                "SELECT scene_number, location, time, content FROM scenes "
                "WHERE episode_id = :ep ORDER BY scene_number"
            ),
            {"ep": ep_id},
        ).fetchall()
        if not rows:
            continue
        payload = []
        for n, loc, t, content in rows:
            head = f"【场景{n}】{loc}"
            if t:
                head += f"·{t}"
            payload.append({"content": f"{head}\n{content or ''}"})
        bind.execute(
            sa.text("UPDATE episodes SET scenes = :s WHERE id = :ep"),
            {"s": json.dumps(payload, ensure_ascii=False), "ep": ep_id},
        )

    # 3. Drop scenes table
    op.drop_table("scenes")
