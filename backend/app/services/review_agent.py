"""Review Agent — takes an episode blob and returns a structured review.

Loads the six-dimension prompt from ``app/skills/review/main.md``, calls the
LLM with a JSON schema constraint, and returns a normalized dict:

    {
        "overall_score": 82.0,   # float 0-100
        "dimensions": {"人物": {"score": 78, "note": "..."}, ...},
        "issues": [{...}, ...],
        "raw": "...",            # raw LLM text (for debugging / audit)
    }

The heavy lifting (parsing / error handling) lives here so the API layer stays
thin. Callers stub :func:`_call_review_llm` in tests to inject a fixture
response without hitting the network.
"""
from __future__ import annotations

import json
from pathlib import Path

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "skills" / "review" / "main.md"


def _load_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return "你是一位剧本审稿编辑。请对提供的剧本进行六维打分，返回 JSON。"


async def _call_review_llm(system_prompt: str, episode_text: str, model_id: str) -> str:
    """Call the LLM in one shot and return its raw response text.

    Split out so tests can monkeypatch it. Uses AgentScope's DashScope /
    DeepSeek / OpenAI / Anthropic ChatModel via :func:`_build_model`.
    """
    from agentscope.message import Msg

    from app.agents.team import _build_model

    model = _build_model(model_id)
    # Force non-streaming for a clean single-response payload
    if hasattr(model, "stream"):
        model.stream = False

    messages = [
        Msg("system", system_prompt, role="system"),
        Msg("user", f"请对以下剧本审稿：\n\n{episode_text}", role="user"),
    ]
    result = await model(messages)
    # AgentScope returns a ChatResponse-like object with a `.content` list
    if hasattr(result, "get_text_content"):
        return result.get_text_content() or ""
    if hasattr(result, "content"):
        # content may be list of blocks
        c = result.content
        if isinstance(c, list):
            return "".join(getattr(b, "text", "") or "" for b in c)
        return str(c or "")
    return str(result)


def _parse_review_json(raw: str) -> dict:
    """Extract the JSON block from the model's response.

    The prompt asks for a fenced ```json ... ``` block. We look for one; if
    absent, try to parse the whole response.
    """
    if not raw:
        return {"overall_score": 0.0, "dimensions": {}, "issues": [], "raw": raw}

    # Try fenced block first
    text = raw
    if "```" in raw:
        # Grab the first ```json ... ``` block
        parts = raw.split("```")
        for i, chunk in enumerate(parts):
            if i == 0:
                continue
            candidate = chunk
            if candidate.startswith("json"):
                candidate = candidate[4:]
            candidate = candidate.strip()
            try:
                text = candidate
                json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue

    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        return {"overall_score": 0.0, "dimensions": {}, "issues": [], "raw": raw}

    return {
        "overall_score": float(parsed.get("overall_score", 0)),
        "dimensions": parsed.get("dimensions", {}) or {},
        "issues": parsed.get("issues", []) or [],
        "raw": raw,
    }


async def review_episode(episode_text: str, model_id: str = "dashscope:qwen-turbo") -> dict:
    """Public entrypoint. Returns a normalized review dict."""
    system_prompt = _load_prompt()
    raw = await _call_review_llm(system_prompt, episode_text, model_id)
    return _parse_review_json(raw)
