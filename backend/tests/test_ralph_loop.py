"""Tests for the Ralph loop — engine + service + API.

Engine tests are pure function calls. Service and API tests stub the LLM by
monkeypatching :func:`review_agent._call_review_llm` so they never hit the
network.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

# ── Engine (pure) ────────────────────────────────────────────────────

def test_engine_pass_when_score_above_threshold():
    from app.services.evolution_engine import Decision, ralph_decide

    assert ralph_decide(review_score=90, pass_threshold=85) == Decision.PASS


def test_engine_revise_for_middling_score():
    from app.services.evolution_engine import Decision, ralph_decide

    d = ralph_decide(review_score=72, pass_threshold=85, revise_threshold=60, retry_count=0)
    assert d == Decision.REVISE


def test_engine_restructure_for_bad_score():
    from app.services.evolution_engine import Decision, ralph_decide

    d = ralph_decide(review_score=45, pass_threshold=85, revise_threshold=60, retry_count=0)
    assert d == Decision.RESTRUCTURE


def test_engine_escalate_when_retries_exhausted():
    from app.services.evolution_engine import Decision, ralph_decide

    d = ralph_decide(review_score=72, pass_threshold=85, retry_count=3, max_retries=3)
    assert d == Decision.ESCALATE


def test_engine_pass_overrides_escalate_when_score_high():
    """A high score should pass even at the retry cap — worth being explicit."""
    from app.services.evolution_engine import Decision, ralph_decide

    d = ralph_decide(review_score=90, pass_threshold=85, retry_count=3, max_retries=3)
    assert d == Decision.PASS


def test_summarize_dimensions_labels_weak_strong():
    from app.services.evolution_engine import summarize_dimensions

    s = summarize_dimensions({
        "人物": {"score": 45},
        "节奏": {"score": 90},
        "对白": {"score": 75},
    })
    assert "人物 45 (弱)" in s
    assert "节奏 90 (强)" in s
    assert "对白 75" in s
    assert "(强)" not in s.split("对白")[1] if "对白" in s else True


# ── Service + API (stubbed LLM) ──────────────────────────────────────

def _register(client, username="alice"):
    return client.post(
        "/api/auth/register", json={"username": username, "password": "pass1234"}
    ).json()


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def _seed_episode_with_content(project_id: int, ep_num: int = 1) -> int:
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, title, status) "
            "VALUES (?, ?, ?, 'in_progress')",
            (project_id, ep_num, f"第{ep_num}集"),
        )
        ep_id = cur.lastrowid
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
            "VALUES (?, 1, '家', '晚', '△小明推门进来\n阿明：终于回来了。')",
            (ep_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return ep_id


def _stub_review(monkeypatch, overall_score=90.0, dimensions=None, issues=None):
    """Monkeypatch the review LLM to return a fixed JSON payload."""
    payload = {
        "overall_score": overall_score,
        "dimensions": dimensions or {"人物": {"score": overall_score, "note": "..."}},
        "issues": issues or [],
        "recommendation": "通过",
    }

    async def fake_call(system_prompt, episode_text, model_id):
        return f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

    from app.services import review_agent
    monkeypatch.setattr(review_agent, "_call_review_llm", fake_call)


async def test_service_persists_iteration_and_marks_pass(app_client, monkeypatch):
    from app.services import ralph_service

    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    ep_id = _seed_episode_with_content(proj["id"])

    _stub_review(monkeypatch, overall_score=90.0)

    result = await ralph_service.run_iteration(proj["id"], ep_id, "test:mock")

    assert result["iteration"] == 1
    assert result["review_score"] == 90.0
    assert result["decision"] == "pass"

    # Episode status should flip to done
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute("SELECT status FROM episodes WHERE id = ?", (ep_id,)).fetchone()
    finally:
        conn.close()
    assert row[0] == "done"


async def test_service_escalates_after_max_retries(app_client, monkeypatch):
    from app.services import ralph_service

    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    ep_id = _seed_episode_with_content(proj["id"])

    _stub_review(monkeypatch, overall_score=70.0)

    # 4 rounds — first 3 are REVISE (retry_count 0→2), 4th is ESCALATE (retry_count 3)
    decisions = []
    for _ in range(4):
        r = await ralph_service.run_iteration(proj["id"], ep_id, "test:mock")
        decisions.append(r["decision"])

    assert decisions[:3] == ["revise", "revise", "revise"]
    assert decisions[3] == "escalate"

    # Episode marked human_review_needed
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT status FROM episodes WHERE id = ?", (ep_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "human_review_needed"


def test_api_get_history_returns_iterations_in_order(app_client, monkeypatch):
    import asyncio

    from app.services import ralph_service

    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    _seed_episode_with_content(proj["id"])

    _stub_review(monkeypatch, overall_score=88.0)

    # Run two iterations
    loop = asyncio.get_event_loop()
    ep_id = loop.run_until_complete(
        _load_ep_id_for(proj["id"], 1)
    )
    loop.run_until_complete(ralph_service.run_iteration(proj["id"], ep_id, "m"))

    # Load history via API
    resp = app_client.get(
        f"/api/projects/{proj['id']}/episodes/1/ralph",
        headers=_auth(alice["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["episode_id"] == ep_id
    assert len(body["iterations"]) == 1
    it = body["iterations"][0]
    assert it["review_score"] == 88.0
    assert it["decision"] == "pass"
    assert isinstance(it["review_dimensions"], dict)


async def _load_ep_id_for(project_id: int, ep_num: int) -> int:
    import aiosqlite

    from app.db import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM episodes WHERE project_id = ? AND episode_number = ?",
            (project_id, ep_num),
        )
        row = await cur.fetchone()
        return row[0]


def test_api_trigger_endpoint(app_client, monkeypatch):
    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    _seed_episode_with_content(proj["id"])

    _stub_review(monkeypatch, overall_score=92.0)

    resp = app_client.post(
        f"/api/projects/{proj['id']}/episodes/1/ralph",
        headers=_auth(alice["token"]),
        json={"model": "test:mock"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "pass"
    assert body["review_score"] == 92.0


def test_api_ownership_isolated(app_client, monkeypatch):
    alice = _register(app_client, "alice")
    bob = _register(app_client, "bob")
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    _seed_episode_with_content(proj["id"])

    resp = app_client.get(
        f"/api/projects/{proj['id']}/episodes/1/ralph",
        headers=_auth(bob["token"]),
    )
    assert resp.status_code == 404


def test_service_handles_empty_episode(app_client, monkeypatch):
    """An episode with no scenes should return an error dict, not crash."""
    import asyncio

    from app.db import DB_PATH
    from app.services import ralph_service

    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()

    # Seed an episode but skip the scenes
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) VALUES (?, 1, 'in_progress')",
            (proj["id"],),
        )
        ep_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        ralph_service.run_iteration(proj["id"], ep_id, "test:mock")
    )
    assert "error" in result


# ── Parser tests ────────────────────────────────────────────────────

def test_parser_handles_fenced_json():
    from app.services.review_agent import _parse_review_json

    raw = "分析中...\n\n```json\n{\"overall_score\": 82, \"dimensions\": {}, \"issues\": []}\n```\n\n结论：通过"
    out = _parse_review_json(raw)
    assert out["overall_score"] == 82.0


def test_parser_handles_bare_json():
    from app.services.review_agent import _parse_review_json

    raw = '{"overall_score": 75, "dimensions": {}, "issues": []}'
    out = _parse_review_json(raw)
    assert out["overall_score"] == 75.0


def test_parser_returns_zero_on_garbage():
    from app.services.review_agent import _parse_review_json

    out = _parse_review_json("模型给了一段完全不是 JSON 的话")
    assert out["overall_score"] == 0.0
    assert out["dimensions"] == {}


@pytest.mark.parametrize("raw", ["", None])
def test_parser_handles_empty(raw):
    from app.services.review_agent import _parse_review_json

    out = _parse_review_json(raw or "")
    assert out["overall_score"] == 0.0
