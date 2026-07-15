"""End-to-end tests: auth flow + project ownership isolation.

Guarantees:
- Register → get a working token
- No-token / bad-token requests to protected endpoints → 401
- User A cannot see or delete User B's projects
"""
from __future__ import annotations


def _register(client, username: str, password: str = "pass1234") -> dict:
    """Register a user, return login-response dict."""
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Auth flow ─────────────────────────────────────────────────────────────

def test_register_returns_token(app_client):
    body = _register(app_client, "alice")
    assert body["token"]
    assert body["nickname"] == "alice"
    assert body["is_new"] is True


def test_login_after_register_works(app_client):
    _register(app_client, "alice")
    resp = app_client.post("/api/auth/login", json={"username": "alice", "password": "pass1234"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["is_new"] is False


# ── Protected endpoints reject missing/bad tokens ────────────────────────

def test_projects_list_without_token_returns_401(app_client):
    resp = app_client.get("/api/projects/list")
    assert resp.status_code == 401


def test_projects_list_with_bad_token_returns_401(app_client):
    resp = app_client.get("/api/projects/list", headers=_auth("not-a-real-token"))
    assert resp.status_code == 401


# ── Ownership isolation ───────────────────────────────────────────────────

def test_projects_list_returns_only_own_projects(app_client):
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")

    # Alice creates a project
    resp = app_client.post(
        "/api/projects/create",
        headers=_auth(alice["token"]),
        json={"title": "Alice-Only", "type": "script", "target_audience": "男频"},
    )
    assert resp.status_code == 200

    # Alice sees her project
    resp = app_client.get("/api/projects/list", headers=_auth(alice["token"]))
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.json()]
    assert "Alice-Only" in titles

    # Bob does not see Alice's project
    resp = app_client.get("/api/projects/list", headers=_auth(bob["token"]))
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.json()]
    assert "Alice-Only" not in titles


def test_get_other_users_project_returns_404(app_client):
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")

    # Alice creates
    resp = app_client.post(
        "/api/projects/create",
        headers=_auth(alice["token"]),
        json={"title": "Alice-Only", "type": "script"},
    )
    pid = resp.json()["id"]

    # Bob tries to GET
    resp = app_client.get(f"/api/projects/{pid}", headers=_auth(bob["token"]))
    assert resp.status_code == 404


def test_delete_other_users_project_returns_404(app_client):
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")

    resp = app_client.post(
        "/api/projects/create",
        headers=_auth(alice["token"]),
        json={"title": "Alice-Only", "type": "script"},
    )
    pid = resp.json()["id"]

    resp = app_client.delete(f"/api/projects/{pid}", headers=_auth(bob["token"]))
    assert resp.status_code == 404

    # Verify Alice's project is still there
    resp = app_client.get(f"/api/projects/{pid}", headers=_auth(alice["token"]))
    assert resp.status_code == 200
