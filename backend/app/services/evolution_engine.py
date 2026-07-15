"""Ralph loop decision engine — pure functions over review scores.

Given the current review score, thresholds and retry count, decide what
happens next:

    Decision
    ────────
    PASS         — score ≥ pass_threshold, episode is done
    REVISE       — score in [revise_threshold, pass_threshold), issue minor
                   fixes, iterate
    RESTRUCTURE  — score < revise_threshold, do a major rewrite
    ESCALATE     — retry_count ≥ max_retries, hand off to the user

Everything here is a pure function. IO (loading iterations, writing new rows,
calling the LLM) lives in the API layer / ralph_service.
"""
from __future__ import annotations

from enum import Enum


class Decision(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    RESTRUCTURE = "restructure"
    ESCALATE = "escalate"


def ralph_decide(
    *,
    review_score: float,
    pass_threshold: float = 85.0,
    revise_threshold: float = 60.0,
    retry_count: int = 0,
    max_retries: int = 3,
) -> Decision:
    """Return the next Ralph action.

    ``retry_count`` is the number of iterations *already run* (0 = fresh
    episode, before the first review). After a review, callers increment
    retry_count and re-run this function to decide the next step.

    Escalation gate has the highest priority — even a passing score will not
    override an over-retry (which shouldn't happen in practice, but the gate
    makes the invariant obvious).
    """
    if review_score >= pass_threshold:
        return Decision.PASS
    if retry_count >= max_retries:
        return Decision.ESCALATE
    if review_score < revise_threshold:
        return Decision.RESTRUCTURE
    return Decision.REVISE


def summarize_dimensions(dimensions: dict[str, dict]) -> str:
    """Build a short human-readable summary of review dimensions.

    Used for UI captions and log lines: "人物 78, 节奏 65 (弱)".
    """
    if not dimensions:
        return ""
    parts: list[str] = []
    for name, payload in dimensions.items():
        if not isinstance(payload, dict):
            continue
        score = payload.get("score")
        if score is None:
            continue
        label = name.strip()
        tag = ""
        try:
            s = float(score)
            if s < 60:
                tag = " (弱)"
            elif s >= 85:
                tag = " (强)"
        except (TypeError, ValueError):
            pass
        parts.append(f"{label} {score}{tag}")
    return ", ".join(parts)
