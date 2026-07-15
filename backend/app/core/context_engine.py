"""Context Engine — inject long-term memory into agent prompts.

Provides ``build_context(project_id, stage, episode_num)`` which pulls
Living Assets (characters + open foreshadows + previous episodes) from the
DB and formats them as a Markdown block the agent can read.

Historical: this module used to also carry ``save_episode_context`` which
regex-scanned generated scripts for character names and foreshadow hints.
That was hallucination-prone (see git log for the P0 issue). Character
creation and foreshadow tracking is now handled explicitly by the agent
tools ``query_characters`` / ``plant_foreshadow`` / ``resolve_foreshadow``
in :mod:`app.agents.team` — the model chooses when to record; we don't
guess from text.
"""
from __future__ import annotations

import aiosqlite

from app.db import DB_PATH


async def build_context(project_id: int, stage: str, episode_num: int = 0) -> str:
    """Build a Markdown memory block for the agent.

    Sections included (in order):
      1. 角色表 — active characters with traits/personality/state/arc
      2. 待回收伏笔 — top 10 open foreshadows by importance × urgency
      3. 前情提要 — last 2 finished episodes (truncated)
    """
    parts: list[str] = []

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # ── Characters ──
        cur = await db.execute(
            "SELECT * FROM characters WHERE project_id = ? AND status != 'deceased' "
            "ORDER BY role",
            (project_id,),
        )
        chars = [dict(c) for c in await cur.fetchall()]
        if chars:
            lines = ["## 角色表"]
            for c in chars:
                line = f"- **{c['name']}**({c.get('role', 'supporting')})"
                if c.get("age"):
                    line += f" {c['age']}岁"
                if c.get("gender"):
                    line += f" {c['gender']}"
                if c.get("traits"):
                    line += f" | 特质:{c['traits']}"
                if c.get("personality"):
                    line += f" | 性格:{c['personality'][:60]}"
                if c.get("current_state"):
                    line += f" | 现状:{c['current_state'][:40]}"
                if c.get("arc"):
                    line += f" | 弧光:{c['arc'][:60]}"
                if c.get("first_appearance"):
                    line += f" | 初登场:{c['first_appearance']}集"
                lines.append(line)
            parts.append("\n".join(lines))

        # ── Foreshadows ──
        cur = await db.execute(
            "SELECT * FROM foreshadows WHERE project_id = ? "
            "AND status IN ('pending','planted') "
            "ORDER BY importance DESC, urgency DESC LIMIT 10",
            (project_id,),
        )
        fores = [dict(f) for f in await cur.fetchall()]
        if fores:
            lines = ["\n## 待回收伏笔"]
            for f in fores:
                emoji = {"pending": "⏳", "planted": "🌱", "partially_resolved": "🔄"}.get(
                    f["status"], "❓"
                )
                line = f"- {emoji} **{f['title']}** [{f.get('category', 'mystery')}] (id={f['id']})"
                if f.get("plant_episode"):
                    line += f" | EP{f['plant_episode']} 埋"
                if f.get("target_episode"):
                    line += f" → EP{f['target_episode']} 回收"
                if f.get("importance", 0) > 0.7:
                    line += " | ⚠ 高重要"
                line += f" | {f['description'][:100]}"
                lines.append(line)
            parts.append("\n".join(lines))

        # ── Previous episodes ──
        # Read scenes table joined to episodes (post-issue #06 shape). Fall back
        # gracefully if an episode has no scene rows yet.
        cur = await db.execute(
            "SELECT id, episode_number, title FROM episodes "
            "WHERE project_id = ? AND status = 'done' "
            "ORDER BY episode_number DESC LIMIT 2",
            (project_id,),
        )
        eps = [dict(e) for e in await cur.fetchall()]
        if eps:
            lines = ["\n## 前情提要"]
            for e in reversed(eps):
                # Grab the first scene's content as a preview
                sc = await db.execute(
                    "SELECT content FROM scenes WHERE episode_id = ? "
                    "ORDER BY scene_number LIMIT 1",
                    (e["id"],),
                )
                row = await sc.fetchone()
                preview = (row["content"] if row and row["content"] else "")[:200]
                lines.append(f"**EP{e['episode_number']}** {e.get('title', '')}\n{preview}")
            parts.append("\n".join(lines))

    return "\n\n".join(parts)
