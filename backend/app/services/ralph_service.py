"""Ralph loop service — glue between the DB, the review agent, and the engine.

Public functions:
- :func:`run_iteration(project_id, episode_id, model_id)` — kick off one
  write→review→decide round; returns the new RalphIteration row + Decision
- :func:`list_iterations(episode_id)` — history for the UI

Read the writing output from the ``scenes`` table (joined into a single blob)
because a Ralph iteration reviews the *whole* episode as delivered.
"""
from __future__ import annotations

import json

import aiosqlite

from app.db import DB_PATH
from app.services.evolution_engine import Decision, ralph_decide
from app.services.review_agent import review_episode


async def _load_project_thresholds(project_id: int) -> dict:
    """Return {pass_threshold, revise_threshold, max_retries} for a project."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT ralph_pass_threshold, ralph_revise_threshold, ralph_max_retries "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = await cur.fetchone()
    if not row:
        return {"pass_threshold": 85.0, "revise_threshold": 60.0, "max_retries": 3}
    return {
        "pass_threshold": row["ralph_pass_threshold"] or 85.0,
        "revise_threshold": row["ralph_revise_threshold"] or 60.0,
        "max_retries": int(row["ralph_max_retries"] or 3),
    }


async def _build_episode_text(episode_id: int) -> str:
    """Assemble the full episode blob from its scenes."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT scene_number, location, time, content FROM scenes "
            "WHERE episode_id = ? ORDER BY scene_number",
            (episode_id,),
        )
        rows = await cur.fetchall()
    if not rows:
        return ""
    chunks: list[str] = []
    for r in rows:
        head = f"【场景{r['scene_number']}】{r['location'] or ''}"
        if r["time"]:
            head += f"·{r['time']}"
        chunks.append(f"{head}\n{r['content'] or ''}")
    return "\n\n".join(chunks)


async def run_iteration(project_id: int, episode_id: int, model_id: str) -> dict:
    """Run one Ralph iteration and persist it.

    Returns the new iteration row (dict) with fields:
      - id, iteration, review_score, decision, review_dimensions, review_issues
    """
    thresholds = await _load_project_thresholds(project_id)
    episode_text = await _build_episode_text(episode_id)
    if not episode_text:
        return {
            "error": "episode has no scenes to review",
            "episode_id": episode_id,
        }

    # 1. Review
    review = await review_episode(episode_text, model_id=model_id)

    # 2. Count prior iterations for the retry gate
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM ralph_iterations WHERE episode_id = ?", (episode_id,)
        )
        retry_count = (await cur.fetchone())[0]

        # 3. Decide
        decision = ralph_decide(
            review_score=review["overall_score"],
            pass_threshold=thresholds["pass_threshold"],
            revise_threshold=thresholds["revise_threshold"],
            retry_count=retry_count,
            max_retries=thresholds["max_retries"],
        )

        # 4. Persist
        cur = await db.execute(
            "INSERT INTO ralph_iterations (episode_id, iteration, writing_output, "
            "review_score, review_dimensions, review_issues, decision) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                episode_id,
                retry_count + 1,
                episode_text,
                review["overall_score"],
                json.dumps(review["dimensions"], ensure_ascii=False),
                json.dumps(review["issues"], ensure_ascii=False),
                decision.value,
            ),
        )
        iteration_id = cur.lastrowid

        # 5. Update episode status when the decision is terminal
        if decision == Decision.PASS:
            await db.execute(
                "UPDATE episodes SET status = 'done', review_score = ? WHERE id = ?",
                (review["overall_score"], episode_id),
            )
        elif decision == Decision.ESCALATE:
            await db.execute(
                "UPDATE episodes SET status = 'human_review_needed' WHERE id = ?",
                (episode_id,),
            )
        await db.commit()

    return {
        "id": iteration_id,
        "iteration": retry_count + 1,
        "review_score": review["overall_score"],
        "review_dimensions": review["dimensions"],
        "review_issues": review["issues"],
        "decision": decision.value,
    }


async def list_iterations(episode_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, iteration, review_score, review_dimensions, review_issues, "
            "decision, created_at FROM ralph_iterations WHERE episode_id = ? "
            "ORDER BY iteration",
            (episode_id,),
        )
        rows = await cur.fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        for k in ("review_dimensions", "review_issues"):
            try:
                d[k] = json.loads(d.get(k) or "null")
            except json.JSONDecodeError:
                d[k] = None
        out.append(d)
    return out
