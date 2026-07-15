"""End-to-end tests for the scene CRUD endpoints.

Uses register → create project → save episode via tool → then hit the
``/scenes`` endpoints as the owner.
"""
from __future__ import annotations


def _register(client, username="alice"):
    resp = client.post("/api/auth/register", json={"username": username, "password": "pass1234"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token, title="P1"):
    resp = client.post(
        "/api/projects/create",
        headers=_auth(token),
        json={"title": title, "type": "script"},
    )
    assert resp.status_code == 200
    return resp.json()


def _seed_episode_with_scenes(project_id, ep_num=1, content=""):
    """Direct DB insert of an episode + scenes — bypasses the LLM path."""
    import sqlite3

    from app.db import DB_PATH
    from app.services.scene_splitter import split_scenes

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, title, status) "
            "VALUES (?, ?, ?, 'done')",
            (project_id, ep_num, f"第{ep_num}集"),
        )
        ep_id = cur.lastrowid
        for s in split_scenes(content):
            conn.execute(
                "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
                "VALUES (?, ?, ?, ?, ?)",
                (ep_id, s["scene_number"], s["location"], s["time"], s["content"]),
            )
        conn.commit()
    finally:
        conn.close()


def test_get_episode_returns_scenes_inline(app_client):
    alice = _register(app_client)
    proj = _create_project(app_client, alice["token"])
    _seed_episode_with_scenes(
        proj["id"], 1,
        "【场景1】咖啡馆·白天\n△推门\n阿明：你终于来了。\n\n"
        "【场景2】街道·夜\n△下雨\n小红：走吧。",
    )

    resp = app_client.get(f"/api/workspace/{proj['id']}/episodes/1", headers=_auth(alice["token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["episode_number"] == 1
    assert len(body["scenes"]) == 2
    assert body["scenes"][0]["location"] == "咖啡馆"
    assert body["scenes"][1]["time"] == "夜"


def test_list_scenes_returns_them_ordered(app_client):
    alice = _register(app_client)
    proj = _create_project(app_client, alice["token"])
    _seed_episode_with_scenes(proj["id"], 1, "【场景1】家·晚\n阿明：走了。")

    resp = app_client.get(
        f"/api/workspace/{proj['id']}/episodes/1/scenes", headers=_auth(alice["token"])
    )
    assert resp.status_code == 200
    scenes = resp.json()
    assert len(scenes) == 1
    assert scenes[0]["scene_number"] == 1


def test_add_scene_appends_at_next_number(app_client):
    alice = _register(app_client)
    proj = _create_project(app_client, alice["token"])
    _seed_episode_with_scenes(proj["id"], 1, "【场景1】家·晚\n阿明：走了。")

    resp = app_client.post(
        f"/api/workspace/{proj['id']}/episodes/1/scenes",
        headers=_auth(alice["token"]),
        json={"location": "地铁", "time": "早上", "content": "△挤地铁"},
    )
    assert resp.status_code == 200
    assert resp.json()["scene_number"] == 2

    resp = app_client.get(
        f"/api/workspace/{proj['id']}/episodes/1/scenes", headers=_auth(alice["token"])
    )
    scenes = resp.json()
    assert [s["scene_number"] for s in scenes] == [1, 2]
    assert scenes[1]["location"] == "地铁"


def test_update_scene_content(app_client):
    alice = _register(app_client)
    proj = _create_project(app_client, alice["token"])
    _seed_episode_with_scenes(proj["id"], 1, "【场景1】家·晚\n阿明：走了。")

    resp = app_client.put(
        f"/api/workspace/{proj['id']}/episodes/1/scenes/1",
        headers=_auth(alice["token"]),
        json={"content": "△新版本\n阿明：不走了。"},
    )
    assert resp.status_code == 200

    scenes = app_client.get(
        f"/api/workspace/{proj['id']}/episodes/1/scenes", headers=_auth(alice["token"])
    ).json()
    assert "不走了" in scenes[0]["content"]


def test_delete_scene(app_client):
    alice = _register(app_client)
    proj = _create_project(app_client, alice["token"])
    _seed_episode_with_scenes(
        proj["id"], 1,
        "【场景1】家·晚\n阿明：走。\n\n【场景2】街·夜\n小红：好。",
    )

    resp = app_client.delete(
        f"/api/workspace/{proj['id']}/episodes/1/scenes/2", headers=_auth(alice["token"])
    )
    assert resp.status_code == 200

    remaining = app_client.get(
        f"/api/workspace/{proj['id']}/episodes/1/scenes", headers=_auth(alice["token"])
    ).json()
    assert [s["scene_number"] for s in remaining] == [1]


def test_scene_ownership_isolated(app_client):
    """Bob cannot list scenes in Alice's project."""
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")
    proj = _create_project(app_client, alice["token"])
    _seed_episode_with_scenes(proj["id"], 1, "【场景1】家·晚\n阿明：走。")

    resp = app_client.get(
        f"/api/workspace/{proj['id']}/episodes/1/scenes", headers=_auth(bob["token"])
    )
    assert resp.status_code == 404
