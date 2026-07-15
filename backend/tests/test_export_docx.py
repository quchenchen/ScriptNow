"""End-to-end .docx export tests.

Round-trips: build a project → seed episodes+scenes → hit the export endpoint
→ parse the returned .docx and assert the expected text is present.
"""
from __future__ import annotations

import io
import sqlite3


def _register(client, username="alice"):
    return client.post(
        "/api/auth/register", json={"username": username, "password": "pass1234"}
    ).json()


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def _seed(project_id: int):
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, title, status) "
            "VALUES (?, 1, '相遇', 'done')",
            (project_id,),
        )
        ep_id = cur.lastrowid
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
            "VALUES (?, 1, '咖啡馆', '白天', ?)",
            (ep_id, "△推门。\n阿明：你终于来了。\n小红：还好吧？"),
        )
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
            "VALUES (?, 2, '街道', '夜', ?)",
            (ep_id, "△下雨。\n阿明：走吧。"),
        )
        conn.commit()
    finally:
        conn.close()


def _extract_docx_text(payload: bytes) -> str:
    """Read the .docx bytes back through python-docx and return concatenated text."""
    from docx import Document
    doc = Document(io.BytesIO(payload))
    return "\n".join(p.text for p in doc.paragraphs)


def test_export_returns_docx_with_scenes(app_client):
    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "TestScript", "type": "script"},
    ).json()
    _seed(proj["id"])

    resp = app_client.post(
        f"/api/projects/{proj['id']}/export?format=docx",
        headers=_auth(alice["token"]),
    )
    assert resp.status_code == 200
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in resp.headers.get("content-disposition", "")

    text = _extract_docx_text(resp.content)
    # Cover
    assert "TestScript" in text
    # Episode heading
    assert "第1集" in text
    assert "相遇" in text
    # Scene headings
    assert "【场景1】咖啡馆·白天" in text
    assert "【场景2】街道·夜" in text
    # Action + dialog content
    assert "推门" in text
    assert "阿明：你终于来了。" in text


def test_export_unsupported_format_returns_400(app_client):
    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "X", "type": "script"},
    ).json()

    resp = app_client.post(
        f"/api/projects/{proj['id']}/export?format=fdx",
        headers=_auth(alice["token"]),
    )
    assert resp.status_code == 400


def test_export_owner_isolation(app_client):
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()

    resp = app_client.post(
        f"/api/projects/{proj['id']}/export?format=docx",
        headers=_auth(bob["token"]),
    )
    assert resp.status_code == 404


def test_export_empty_project_returns_docx_with_cover_only(app_client):
    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "EmptyOne", "type": "script"},
    ).json()

    resp = app_client.post(
        f"/api/projects/{proj['id']}/export?format=docx",
        headers=_auth(alice["token"]),
    )
    assert resp.status_code == 200
    text = _extract_docx_text(resp.content)
    assert "EmptyOne" in text  # Cover title still rendered
