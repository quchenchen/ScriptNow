"""HTTP-level tests for the sources API."""
from __future__ import annotations

import io

import pytest


def _register(client, name: str = "alice") -> str:
    r = client.post("/api/auth/register", json={"username": name, "password": "pass1234"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _make_project(client, token: str) -> int:
    r = client.post(
        "/api/projects/create",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "改编版《巷子里的诗人》",
            "type": "script",
            "genre": '["都市","悬疑"]',
            "source_mode": "adapted",
            "original_work": "《巷子里的诗人》",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def upload_root_redirect(monkeypatch, tmp_path):
    """Point ``source_indexer.UPLOAD_ROOT`` at tmp so we don't touch repo."""
    from app.services import source_indexer
    monkeypatch.setattr(source_indexer, "UPLOAD_ROOT", tmp_path / "uploads")
    return tmp_path / "uploads"


def test_upload_source_returns_pending(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    r = app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("outline.txt", io.BytesIO("剧情大纲第一稿。第二段。".encode()), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in {"pending", "done"}
    assert body["filename"] == "outline.txt"


def test_upload_rejects_unsupported_extension(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    r = app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("mystery.rtf", io.BytesIO(b"nope"), "application/rtf")},
    )
    assert r.status_code == 400
    assert "格式" in r.json()["detail"]


def test_upload_rejects_empty_file(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    r = app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("blank.txt", io.BytesIO(b""), "text/plain")},
    )
    assert r.status_code == 400


def test_upload_ownership_enforced(app_client, upload_root_redirect):
    token_a = _register(app_client, "alice")
    token_b = _register(app_client, "bob")
    pid_a = _make_project(app_client, token_a)

    r = app_client.post(
        f"/api/projects/{pid_a}/sources/upload",
        headers=_hdrs(token_b),
        files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert r.status_code == 404  # OwnedProject hides existence


def test_list_and_get_after_upload(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    up = app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("scene.md", io.BytesIO("# 场景一\n\n内容内容内容".encode()), "text/markdown")},
    ).json()

    listed = app_client.get(f"/api/projects/{pid}/sources", headers=_hdrs(token)).json()
    assert any(s["filename"] == "scene.md" for s in listed)

    detail = app_client.get(
        f"/api/projects/{pid}/sources/{up['id']}", headers=_hdrs(token),
    ).json()
    assert detail["filename"] == "scene.md"
    assert "preview_chunks" in detail


def test_delete_removes_source(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    up = app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("t.txt", io.BytesIO("abc".encode()), "text/plain")},
    ).json()

    r = app_client.delete(
        f"/api/projects/{pid}/sources/{up['id']}", headers=_hdrs(token),
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == up["id"]

    listed = app_client.get(f"/api/projects/{pid}/sources", headers=_hdrs(token)).json()
    assert not any(s["id"] == up["id"] for s in listed)


def test_project_wide_search_endpoint(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("a.txt", io.BytesIO(
            "。".join(["侦探在雨夜追踪嫌疑人" for _ in range(6)]).encode()
        ), "text/plain")},
    )

    r = app_client.get(
        f"/api/projects/{pid}/sources-search",
        headers=_hdrs(token),
        params={"q": "侦探 追踪", "k": 3},
    )
    assert r.status_code == 200
    hits = r.json()
    assert hits, "expected at least one hit"
    assert "preview" in hits[0]
    assert "chunk_id" in hits[0]


def test_expand_chunk_endpoint(app_client, upload_root_redirect):
    token = _register(app_client)
    pid = _make_project(app_client, token)

    long_text = "。".join(f"内容段 {i} 用于测试展开" for i in range(20)) + "。"
    up = app_client.post(
        f"/api/projects/{pid}/sources/upload",
        headers=_hdrs(token),
        files={"file": ("l.txt", io.BytesIO(long_text.encode()), "text/plain")},
    ).json()

    # Pull chunk id from search
    hits = app_client.get(
        f"/api/projects/{pid}/sources-search",
        headers=_hdrs(token),
        params={"q": "内容段", "k": 1},
    ).json()
    assert hits
    chunk_id = hits[0]["chunk_id"]

    r = app_client.get(
        f"/api/projects/{pid}/chunks/{chunk_id}",
        headers=_hdrs(token),
        params={"ctx": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["chunk_id"] == chunk_id
    assert "context" in body
    _ = up
