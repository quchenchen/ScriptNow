"""End-to-end tests for Character / Foreshadow / Prop endpoints.

Focus:
- Prop CRUD
- Foreshadow state machine via PATCH endpoint
- ``is_overdue`` annotation on GET foreshadows
- Character dirty-episodes preview (uses growth tree)
"""
from __future__ import annotations

import sqlite3


def _register(client, username="alice"):
    resp = client.post("/api/auth/register", json={"username": username, "password": "pass1234"})
    return resp.json()


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def _create(client, token, title="P"):
    return client.post(
        "/api/projects/create", headers=_auth(token),
        json={"title": title, "type": "script"},
    ).json()


# ── Prop CRUD ────────────────────────────────────────────────────────

def test_prop_crud_round_trip(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])

    resp = app_client.post(
        f"/api/memory/{p['id']}/props",
        headers=_auth(alice["token"]),
        json={"name": "怀表", "description": "父亲遗物", "significance": "macguffin"},
    )
    assert resp.status_code == 200
    prop_id = resp.json()["id"]

    resp = app_client.get(f"/api/memory/{p['id']}/props", headers=_auth(alice["token"]))
    assert resp.status_code == 200
    props = resp.json()
    assert len(props) == 1
    assert props[0]["name"] == "怀表"
    assert props[0]["significance"] == "macguffin"

    resp = app_client.put(
        f"/api/memory/{p['id']}/props/{prop_id}",
        headers=_auth(alice["token"]),
        json={"description": "父亲遗物·刻有密码"},
    )
    assert resp.status_code == 200

    resp = app_client.get(f"/api/memory/{p['id']}/props", headers=_auth(alice["token"]))
    assert "密码" in resp.json()[0]["description"]

    resp = app_client.delete(
        f"/api/memory/{p['id']}/props/{prop_id}", headers=_auth(alice["token"])
    )
    assert resp.status_code == 200

    resp = app_client.get(f"/api/memory/{p['id']}/props", headers=_auth(alice["token"]))
    assert resp.json() == []


def test_prop_significance_filter(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])

    for name, sig in [("A", "background"), ("B", "plot_device"), ("C", "macguffin")]:
        app_client.post(
            f"/api/memory/{p['id']}/props",
            headers=_auth(alice["token"]),
            json={"name": name, "significance": sig},
        )

    resp = app_client.get(
        f"/api/memory/{p['id']}/props?significance=macguffin",
        headers=_auth(alice["token"]),
    )
    names = [pp["name"] for pp in resp.json()]
    assert names == ["C"]


def test_prop_owner_isolation(app_client):
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")
    p = _create(app_client, alice["token"])

    resp = app_client.get(f"/api/memory/{p['id']}/props", headers=_auth(bob["token"]))
    assert resp.status_code == 404


# ── Foreshadow state transitions via PATCH ──────────────────────────

def test_foreshadow_transition_planted_to_resolved(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])

    # Seed a planted foreshadow directly
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO foreshadows (project_id, title, description, status, target_episode) "
            "VALUES (?, '怀表', '藏着秘密', 'planted', 10)",
            (p["id"],),
        )
        fid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    resp = app_client.patch(
        f"/api/memory/{p['id']}/foreshadows/{fid}/status",
        headers=_auth(alice["token"]),
        json={"target": "resolved", "resolution_text": "第10集揭示"},
    )
    assert resp.status_code == 200
    assert resp.json()["new_state"] == "resolved"


def test_foreshadow_illegal_transition_rejected(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO foreshadows (project_id, title, description, status) "
            "VALUES (?, 'X', 'x', 'resolved')",
            (p["id"],),
        )
        fid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    resp = app_client.patch(
        f"/api/memory/{p['id']}/foreshadows/{fid}/status",
        headers=_auth(alice["token"]),
        json={"target": "planted"},
    )
    assert resp.status_code == 400


def test_foreshadow_list_annotates_is_overdue(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])

    # Seed: 1 episode at ep=6, foreshadow with target_episode=10 & remind_before=5
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) VALUES (?, 6, 'done')",
            (p["id"],),
        )
        conn.execute(
            "INSERT INTO foreshadows (project_id, title, description, status, "
            "target_episode, remind_before) VALUES (?, 'X', 'x', 'planted', 10, 5)",
            (p["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    resp = app_client.get(
        f"/api/memory/{p['id']}/foreshadows", headers=_auth(alice["token"])
    )
    fores = resp.json()
    assert len(fores) == 1
    assert fores[0]["is_overdue"] is True


# ── Character cascade preview ───────────────────────────────────────

def test_character_dirty_episodes_via_growth_tree(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])

    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO characters (project_id, name, role) VALUES (?, '阿明', 'protagonist')",
            (p["id"],),
        )
        char_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) VALUES (?, 1, 'done')",
            (p["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    # Backfill the growth tree so character node exists
    resp = app_client.post(
        f"/api/projects/{p['id']}/tree/backfill", headers=_auth(alice["token"])
    )
    assert resp.status_code == 200

    resp = app_client.get(
        f"/api/memory/{p['id']}/characters/{char_id}/dirty-episodes",
        headers=_auth(alice["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["character_id"] == char_id
    # Character node → references → first episode; expect at least 1 affected
    assert len(body["affected"]) >= 1
    assert body["affected"][0]["node_type"] == "episode"


# ── /memory summary includes props ───────────────────────────────────

def test_memory_summary_includes_props(app_client):
    alice = _register(app_client)
    p = _create(app_client, alice["token"])
    app_client.post(
        f"/api/memory/{p['id']}/props",
        headers=_auth(alice["token"]),
        json={"name": "怀表", "significance": "macguffin"},
    )
    resp = app_client.get(f"/api/memory/{p['id']}/memory", headers=_auth(alice["token"]))
    body = resp.json()
    assert set(body.keys()) == {"characters", "foreshadows", "scenes", "props"}
    assert body["props"][0]["name"] == "怀表"
