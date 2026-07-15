"""Growth Tree service — pure-ish functions over the growth_nodes + growth_edges tables.

Public surface:
- :func:`get_tree(project_id)` — full nodes+edges snapshot
- :func:`lineage(node_id)` — all ancestors (upstream through outgoing edges FROM this node)
- :func:`descendants(node_id)` — all downstream nodes (transitively)
- :func:`mark_dirty(source_node_id)` — set of downstream episode / scene node ids affected

Edge direction convention:
- An edge ``A → B`` with ``edge_type='derived_from'`` reads "B was derived from A".
- So descendants of A = nodes reachable following outgoing edges from A.
- Lineage of B = nodes reachable following *incoming* edges to B.

Also provides tiny recorders for the write side:
- :func:`record_artefact(...)` — insert a node
- :func:`record_derived_from(...)` — insert an edge
Both are idempotent-ish (return existing id if the same (type, ref_id) is
already recorded for the project).
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass

import aiosqlite

from app.db import DB_PATH


@dataclass
class NodeRow:
    id: int
    project_id: int
    node_type: str
    ref_id: int | None
    label: str
    metadata: dict


@dataclass
class EdgeRow:
    id: int
    from_node_id: int
    to_node_id: int
    edge_type: str


def _decode_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _row_to_node(r) -> NodeRow:
    return NodeRow(
        id=r["id"], project_id=r["project_id"], node_type=r["node_type"],
        ref_id=r["ref_id"], label=r["label"] or "",
        metadata=_decode_metadata(r["metadata"]),
    )


def _row_to_edge(r) -> EdgeRow:
    return EdgeRow(
        id=r["id"], from_node_id=r["from_node_id"], to_node_id=r["to_node_id"],
        edge_type=r["edge_type"],
    )


# ── Reads ─────────────────────────────────────────────────────────────

async def get_tree(project_id: int) -> dict:
    """Return ``{"nodes": [...], "edges": [...]}`` for the project."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        node_cur = await db.execute(
            "SELECT id, project_id, node_type, ref_id, label, metadata "
            "FROM growth_nodes WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
        nodes = [_row_to_node(r) for r in await node_cur.fetchall()]
        edge_cur = await db.execute(
            "SELECT id, from_node_id, to_node_id, edge_type "
            "FROM growth_edges WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
        edges = [_row_to_edge(r) for r in await edge_cur.fetchall()]
    return {
        "nodes": [n.__dict__ for n in nodes],
        "edges": [e.__dict__ for e in edges],
    }


async def _load_project_edges(project_id: int) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Return (forward_adj, reverse_adj) mapping node_id → list of neighbor ids."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT from_node_id, to_node_id FROM growth_edges WHERE project_id = ?",
            (project_id,),
        )
        rows = await cur.fetchall()
    forward: dict[int, list[int]] = {}
    reverse: dict[int, list[int]] = {}
    for r in rows:
        forward.setdefault(r["from_node_id"], []).append(r["to_node_id"])
        reverse.setdefault(r["to_node_id"], []).append(r["from_node_id"])
    return forward, reverse


async def _load_node(node_id: int) -> NodeRow | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, project_id, node_type, ref_id, label, metadata "
            "FROM growth_nodes WHERE id = ?",
            (node_id,),
        )
        row = await cur.fetchone()
    return _row_to_node(row) if row else None


def _bfs(start_id: int, adj: dict[int, list[int]]) -> list[int]:
    """BFS from start_id following ``adj``, returning visited node ids (excluding start)."""
    seen: set[int] = {start_id}
    order: list[int] = []
    q: deque[int] = deque(adj.get(start_id, []))
    while q:
        n = q.popleft()
        if n in seen:
            continue
        seen.add(n)
        order.append(n)
        for m in adj.get(n, []):
            if m not in seen:
                q.append(m)
    return order


async def lineage(node_id: int) -> list[NodeRow]:
    """All ancestors of ``node_id`` (transitively), oldest first (root → parent)."""
    node = await _load_node(node_id)
    if not node:
        return []
    _, reverse = await _load_project_edges(node.project_id)
    ancestor_ids = _bfs(node_id, reverse)
    if not ancestor_ids:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(ancestor_ids))
        cur = await db.execute(
            f"SELECT id, project_id, node_type, ref_id, label, metadata "
            f"FROM growth_nodes WHERE id IN ({placeholders})",
            ancestor_ids,
        )
        rows = {r["id"]: _row_to_node(r) for r in await cur.fetchall()}
    # Return in BFS order (parent-of-parent last, immediate parent first).
    # For UI display we usually want root → node; reverse before returning.
    return [rows[i] for i in reversed(ancestor_ids) if i in rows]


async def descendants(node_id: int) -> list[NodeRow]:
    """All descendants of ``node_id`` (transitively), BFS order."""
    node = await _load_node(node_id)
    if not node:
        return []
    forward, _ = await _load_project_edges(node.project_id)
    desc_ids = _bfs(node_id, forward)
    if not desc_ids:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(desc_ids))
        cur = await db.execute(
            f"SELECT id, project_id, node_type, ref_id, label, metadata "
            f"FROM growth_nodes WHERE id IN ({placeholders})",
            desc_ids,
        )
        rows = {r["id"]: _row_to_node(r) for r in await cur.fetchall()}
    return [rows[i] for i in desc_ids if i in rows]


async def mark_dirty(source_node_id: int) -> list[NodeRow]:
    """Return the downstream episode/scene nodes affected by a source change.

    We don't actually write a dirty flag yet (that's issue #07's cascade
    marker table); we just compute the set so callers can display or persist
    it. Filters to ``episode`` / ``scene`` nodes because those are the
    user-visible artefacts a Living Asset change would demand rewriting.
    """
    desc = await descendants(source_node_id)
    return [n for n in desc if n.node_type in ("episode", "scene")]


# ── Writes ────────────────────────────────────────────────────────────

async def record_artefact(
    project_id: int,
    node_type: str,
    ref_id: int | None,
    label: str = "",
    metadata: dict | None = None,
) -> int:
    """Insert a growth_node. Returns the (existing or new) node id.

    Idempotency: if a node with the same (project_id, node_type, ref_id)
    already exists, we return its id and don't insert.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if ref_id is not None:
            cur = await db.execute(
                "SELECT id FROM growth_nodes "
                "WHERE project_id = ? AND node_type = ? AND ref_id = ?",
                (project_id, node_type, ref_id),
            )
            existing = await cur.fetchone()
            if existing:
                return existing["id"]

        cur = await db.execute(
            "INSERT INTO growth_nodes (project_id, node_type, ref_id, label, metadata) "
            "VALUES (?,?,?,?,?)",
            (project_id, node_type, ref_id, label,
             json.dumps(metadata or {}, ensure_ascii=False)),
        )
        await db.commit()
        return cur.lastrowid


async def record_derived_from(
    project_id: int,
    from_node_id: int,
    to_node_id: int,
    edge_type: str = "derived_from",
) -> int:
    """Insert an edge ``from → to``. Idempotent on (from, to, type)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM growth_edges "
            "WHERE from_node_id = ? AND to_node_id = ? AND edge_type = ?",
            (from_node_id, to_node_id, edge_type),
        )
        existing = await cur.fetchone()
        if existing:
            return existing["id"]
        cur = await db.execute(
            "INSERT INTO growth_edges (project_id, from_node_id, to_node_id, edge_type) "
            "VALUES (?,?,?,?)",
            (project_id, from_node_id, to_node_id, edge_type),
        )
        await db.commit()
        return cur.lastrowid


async def find_node(project_id: int, node_type: str, ref_id: int) -> NodeRow | None:
    """Look up an existing node by ``(project_id, node_type, ref_id)``."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, project_id, node_type, ref_id, label, metadata FROM growth_nodes "
            "WHERE project_id = ? AND node_type = ? AND ref_id = ?",
            (project_id, node_type, ref_id),
        )
        row = await cur.fetchone()
    return _row_to_node(row) if row else None


# ── Backfill (for existing projects) ─────────────────────────────────

async def backfill_project(project_id: int) -> dict:
    """Rebuild a growth tree from existing project data.

    Chain: idea → structure → outline → episode → scene(s). Assets (characters,
    foreshadows) become nodes with ``references`` edges to the earliest episode.
    Idempotent — call multiple times safely.

    Returns a summary dict for logging.
    """
    summary = {"nodes_created": 0, "edges_created": 0}

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. Idea node — one per project (ref_id points at project)
        idea_id = await record_artefact(project_id, "idea", project_id, label="项目起点")
        summary["nodes_created"] += 1

        # 2. Stage outputs (script_versions) — chain by insertion order
        cur = await db.execute(
            "SELECT id, stage, agent_name FROM script_versions "
            "WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
        versions = await cur.fetchall()
        prev_stage_node = idea_id
        for v in versions:
            node_type = "structure" if v["stage"] in ("structure", "story_design") else "outline"
            n_id = await record_artefact(
                project_id, node_type, v["id"],
                label=f"{v['stage']}({v['agent_name'] or 'Agent'})",
            )
            await record_derived_from(project_id, prev_stage_node, n_id)
            summary["nodes_created"] += 1
            summary["edges_created"] += 1
            prev_stage_node = n_id

        # 3. Episodes → Scenes
        cur = await db.execute(
            "SELECT id, episode_number, title FROM episodes "
            "WHERE project_id = ? ORDER BY episode_number",
            (project_id,),
        )
        episodes = await cur.fetchall()
        for ep in episodes:
            ep_node = await record_artefact(
                project_id, "episode", ep["id"],
                label=f"EP{ep['episode_number']} {ep['title'] or ''}",
            )
            await record_derived_from(project_id, prev_stage_node, ep_node)
            summary["nodes_created"] += 1
            summary["edges_created"] += 1

            sc_cur = await db.execute(
                "SELECT id, scene_number, location FROM scenes "
                "WHERE episode_id = ? ORDER BY scene_number",
                (ep["id"],),
            )
            for sc in await sc_cur.fetchall():
                sc_node = await record_artefact(
                    project_id, "scene", sc["id"],
                    label=f"S{sc['scene_number']} {sc['location'] or ''}",
                )
                await record_derived_from(project_id, ep_node, sc_node)
                summary["nodes_created"] += 1
                summary["edges_created"] += 1

        # 4. Assets — characters + foreshadows point at the first episode via references
        first_ep = episodes[0] if episodes else None
        if first_ep:
            first_ep_node = await record_artefact(project_id, "episode", first_ep["id"])
            for tbl in ("characters", "foreshadows"):
                col = "name" if tbl == "characters" else "title"
                asset_cur = await db.execute(
                    f"SELECT id, {col} FROM {tbl} WHERE project_id = ?",
                    (project_id,),
                )
                for row in await asset_cur.fetchall():
                    a_node = await record_artefact(
                        project_id, "asset", row["id"],
                        label=f"{tbl[:-1]}:{row[col]}",
                    )
                    await record_derived_from(
                        project_id, a_node, first_ep_node, edge_type="references"
                    )
                    summary["nodes_created"] += 1
                    summary["edges_created"] += 1

    return summary
