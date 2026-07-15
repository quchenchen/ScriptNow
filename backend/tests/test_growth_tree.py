"""Tests for the growth tree service + API.

Covers:
- Pure BFS functions (lineage / descendants / mark_dirty)
- Idempotent record_artefact / record_derived_from
- Backfill on a synthetic project
- API endpoints + owner isolation
"""
from __future__ import annotations

import sqlite3

import pytest


def _register(client, username="alice"):
    resp = client.post("/api/auth/register", json={"username": username, "password": "pass1234"})
    assert resp.status_code == 200
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def project_id(app_client):
    """Create a project and return its id (owned by ``alice``)."""
    alice = _register(app_client, "alice")
    resp = app_client.post(
        "/api/projects/create",
        headers=_auth(alice["token"]),
        json={"title": "TreeProject", "type": "script"},
    )
    return resp.json()["id"]


# ── Service-level (pure-ish) tests ───────────────────────────────────

async def test_record_artefact_is_idempotent(project_id):
    from app.services import growth_tree_service as svc

    a = await svc.record_artefact(project_id, "idea", project_id, label="X")
    b = await svc.record_artefact(project_id, "idea", project_id, label="Y")
    assert a == b


async def test_record_derived_from_is_idempotent(project_id):
    from app.services import growth_tree_service as svc

    n1 = await svc.record_artefact(project_id, "idea", project_id)
    n2 = await svc.record_artefact(project_id, "structure", 100)
    e1 = await svc.record_derived_from(project_id, n1, n2)
    e2 = await svc.record_derived_from(project_id, n1, n2)
    assert e1 == e2


async def test_lineage_returns_root_to_parent(project_id):
    from app.services import growth_tree_service as svc

    # idea → structure → episode
    idea = await svc.record_artefact(project_id, "idea", project_id, label="idea")
    struct = await svc.record_artefact(project_id, "structure", 1, label="struct")
    ep = await svc.record_artefact(project_id, "episode", 1, label="ep")
    await svc.record_derived_from(project_id, idea, struct)
    await svc.record_derived_from(project_id, struct, ep)

    ancestors = await svc.lineage(ep)
    # Root → parent
    assert [n.label for n in ancestors] == ["idea", "struct"]


async def test_descendants_returns_bfs_order(project_id):
    from app.services import growth_tree_service as svc

    root = await svc.record_artefact(project_id, "idea", project_id, label="root")
    a = await svc.record_artefact(project_id, "structure", 1, label="a")
    b = await svc.record_artefact(project_id, "structure", 2, label="b")
    c = await svc.record_artefact(project_id, "episode", 1, label="c")
    await svc.record_derived_from(project_id, root, a)
    await svc.record_derived_from(project_id, root, b)
    await svc.record_derived_from(project_id, a, c)

    descs = await svc.descendants(root)
    labels = [n.label for n in descs]
    # BFS: children first (a, b), then grandchildren (c)
    assert labels == ["a", "b", "c"]


async def test_mark_dirty_only_returns_episodes_and_scenes(project_id):
    from app.services import growth_tree_service as svc

    idea = await svc.record_artefact(project_id, "idea", project_id, label="idea")
    struct = await svc.record_artefact(project_id, "structure", 1, label="struct")
    ep = await svc.record_artefact(project_id, "episode", 1, label="ep")
    sc = await svc.record_artefact(project_id, "scene", 1, label="sc")
    asset = await svc.record_artefact(project_id, "asset", 1, label="asset")
    await svc.record_derived_from(project_id, idea, struct)
    await svc.record_derived_from(project_id, struct, ep)
    await svc.record_derived_from(project_id, ep, sc)
    await svc.record_derived_from(project_id, ep, asset)

    affected = await svc.mark_dirty(idea)
    types = sorted({n.node_type for n in affected})
    assert types == ["episode", "scene"]
    # asset should NOT be in the affected set even though it's downstream
    assert not any(n.node_type == "asset" for n in affected)


async def test_backfill_creates_expected_nodes(project_id, app_client):
    """Seed a synthetic project with episodes + scenes + characters, then backfill."""
    from app.db import DB_PATH
    from app.services import growth_tree_service as svc

    conn = sqlite3.connect(str(DB_PATH))
    try:
        # Insert 1 episode with 2 scenes and 1 character
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, title, status) "
            "VALUES (?, 1, '第1集', 'done')",
            (project_id,),
        )
        ep_id = cur.lastrowid
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, content) "
            "VALUES (?, 1, '家', '△出门'), (?, 2, '街', '△下雨')",
            (ep_id, ep_id),
        )
        conn.execute(
            "INSERT INTO characters (project_id, name, role) VALUES (?, '阿明', 'protagonist')",
            (project_id,),
        )
        conn.commit()
    finally:
        conn.close()

    summary = await svc.backfill_project(project_id)

    # 1 idea + 1 episode + 2 scenes + 1 asset = at least 5
    assert summary["nodes_created"] >= 5

    tree = await svc.get_tree(project_id)
    types = sorted({n["node_type"] for n in tree["nodes"]})
    assert types == ["asset", "episode", "idea", "scene"]


# ── API-level tests ──────────────────────────────────────────────────

def test_get_tree_requires_auth(app_client, project_id):
    resp = app_client.get(f"/api/projects/{project_id}/tree")
    assert resp.status_code == 401


def test_get_tree_isolated_by_owner(app_client, project_id):
    bob = _register(app_client, "bob")
    resp = app_client.get(
        f"/api/projects/{project_id}/tree", headers=_auth(bob["token"])
    )
    assert resp.status_code == 404


def test_backfill_then_get_tree(app_client):
    alice = _register(app_client, "alice")
    proj = app_client.post(
        "/api/projects/create",
        headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()

    # Seed one episode+scene directly
    import sqlite3

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) VALUES (?, 1, 'done')",
            (proj["id"],),
        )
        ep_id = cur.lastrowid
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, content) "
            "VALUES (?, 1, '家', '')",
            (ep_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Backfill
    resp = app_client.post(
        f"/api/projects/{proj['id']}/tree/backfill", headers=_auth(alice["token"])
    )
    assert resp.status_code == 200
    assert resp.json()["nodes_created"] >= 3

    # Read tree
    resp = app_client.get(
        f"/api/projects/{proj['id']}/tree", headers=_auth(alice["token"])
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) >= 3
    assert len(body["edges"]) >= 2  # idea→episode, episode→scene


def test_mark_dirty_endpoint(app_client, project_id):
    alice_tok = None
    for user in ("alice",):
        # alice was created via project_id fixture; retrieve token by logging in
        alice_tok = app_client.post(
            "/api/auth/login", json={"username": "alice", "password": "pass1234"}
        ).json()["token"]

    import asyncio

    from app.services import growth_tree_service as svc

    async def seed():
        idea = await svc.record_artefact(project_id, "idea", project_id, label="idea")
        ep = await svc.record_artefact(project_id, "episode", 1, label="ep")
        await svc.record_derived_from(project_id, idea, ep)
        return idea

    idea_node_id = asyncio.get_event_loop().run_until_complete(seed())

    resp = app_client.post(
        f"/api/projects/{project_id}/tree/mark-dirty",
        headers=_auth(alice_tok),
        json={"source_node_id": idea_node_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_node_id"] == idea_node_id
    assert len(body["affected_nodes"]) == 1
    assert body["affected_nodes"][0]["node_type"] == "episode"
