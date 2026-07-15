"""Integration: Ralph loop merges detector issues + docks score on AI-tell."""
from __future__ import annotations

import json
import sqlite3


def _register(client, username="alice"):
    return client.post(
        "/api/auth/register", json={"username": username, "password": "pass1234"}
    ).json()


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def _stub_review_high_score(monkeypatch, score=90.0):
    """Stub the LLM to always return a passing review."""
    payload = {
        "overall_score": score,
        "dimensions": {"人物": {"score": score, "note": "..."}},
        "issues": [],
        "recommendation": "通过",
    }

    async def fake(system_prompt, episode_text, model_id):
        return f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

    from app.services import review_agent
    monkeypatch.setattr(review_agent, "_call_review_llm", fake)


def _seed_ai_ai_tell_episode(project_id: int) -> int:
    """Episode whose scene content is heavy AI-tell prose."""
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) "
            "VALUES (?, 1, 'in_progress')",
            (project_id,),
        )
        ep_id = cur.lastrowid
        # Heavy AI-tell content: filler words + inner monologue
        content = (
            "阿明竟然没回来。突然，门开了。然而没有人。其实他一直都在。"
            "原来一切都是误会。终于，居然，不禁让人难过。反正就是这样。"
            "他心想她怎么还没来。他暗想是不是走错了。内心一阵慌乱。"
            "他自言自语地嘀咕着。心里想的是那天的雨。暗自懊悔。"
        )
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
            "VALUES (?, 1, '家', '晚', ?)",
            (ep_id, content),
        )
        conn.commit()
    finally:
        conn.close()
    return ep_id


def _seed_clean_episode(project_id: int) -> int:
    from app.db import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "INSERT INTO episodes (project_id, episode_number, status) "
            "VALUES (?, 1, 'in_progress')",
            (project_id,),
        )
        ep_id = cur.lastrowid
        conn.execute(
            "INSERT INTO scenes (episode_id, scene_number, location, time, content) "
            "VALUES (?, 1, '家', '晚', ?)",
            (
                ep_id,
                "小红：你来了。\n阿明：等很久了吗？\n小红：还好。\n"
                "△她把咖啡推过去。\n阿明：谢谢。\n小红：说吧，什么事。\n"
                "阿明：我要走了。下周去纽约。\n小红：多久？\n阿明：三年。也许更久。",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return ep_id


async def test_ai_tell_episode_gets_detector_issues_and_score_penalty(
    app_client, monkeypatch,
):
    from app.services import ralph_service

    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    ep_id = _seed_ai_ai_tell_episode(proj["id"])

    _stub_review_high_score(monkeypatch, score=90.0)

    result = await ralph_service.run_iteration(proj["id"], ep_id, "test:mock")

    # Score docked below the pure 90 the review agent returned
    assert result["review_score"] < 90.0
    # Detector issues merged into review issues
    types = {iss["type"] for iss in result["review_issues"]}
    assert types & {"filler_word_overuse", "inner_monologue_overuse", "sentence_rhythm_uniform"}


async def test_clean_episode_keeps_full_review_score(app_client, monkeypatch):
    from app.services import ralph_service

    alice = _register(app_client)
    proj = app_client.post(
        "/api/projects/create", headers=_auth(alice["token"]),
        json={"title": "P", "type": "script"},
    ).json()
    ep_id = _seed_clean_episode(proj["id"])

    _stub_review_high_score(monkeypatch, score=90.0)

    result = await ralph_service.run_iteration(proj["id"], ep_id, "test:mock")
    assert result["review_score"] == 90.0  # No penalty
    # No detector issues (clean text)
    types = {iss["type"] for iss in result["review_issues"]}
    assert not (types & {"filler_word_overuse", "inner_monologue_overuse"})
