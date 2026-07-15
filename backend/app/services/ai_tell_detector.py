"""AI-tell detector — heuristics that catch machine-written prose.

We look at three signals:

1. **Filler word density.** LLMs over-use narrative connectives ("竟然", "然而",
   "突然", "其实", …). In good drama they should appear sparingly.
2. **Inner-monologue markers.** "心想", "暗想", "内心" — AI leans hard on these
   to explain a character; good screenwriting *shows* instead.
3. **Sentence-length uniformity.** Human-written drama alternates short punchy
   lines (dialog) with longer action beats. LLMs tend toward uniform mid-length
   sentences. We compute the coefficient of variation of sentence length; a
   very low CV = suspiciously even rhythm.

Output shape (call it "AITellReport")::

    {
        "score": 0-100,          # higher = healthier / less AI-tell
        "sentence_count": int,
        "issues": [
            {
                "type": "filler_word_overuse" | "inner_monologue_overuse"
                        | "sentence_rhythm_uniform",
                "severity": "high" | "medium" | "low",
                "count": int,
                "examples": [str, ...]  # first 3 offenders
            }, ...
        ]
    }

The detector is a pure function of a text blob. No LLM call. The optional
LLM-judge escalation from the PRD (issue #13) is deferred to a follow-up.
"""
from __future__ import annotations

import re
import statistics
from typing import Any

# Words that LLMs over-use in Chinese short-drama prose. Curated from
# empirical inspection of generated episodes. Weights are the per-1000-char
# thresholds above which we flag the word (0 = never flag alone; combined
# density matters).
FILLER_WORDS: dict[str, int] = {
    "竟然": 3,
    "然而": 3,
    "突然": 3,
    "终于": 3,
    "其实": 3,
    "原来": 3,
    "居然": 3,
    "不禁": 2,
    "不由得": 2,
    "反正": 2,
    "于是": 3,
    "却": 4,  # this one is common in Chinese; higher threshold
    "只是": 4,
    "但是": 4,
    "所以": 4,
    "此时": 2,
    "此刻": 2,
    "顿时": 2,
}

INNER_MONOLOGUE_MARKERS: list[str] = [
    "心想",
    "暗想",
    "内心",
    "在心里",
    "自言自语",
    "暗自",
    "心中想到",
    "心里想",
]

# Approximate sentence delimiter for Chinese prose
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?\n]+")


def _severity_from_count(count: int, thresholds: tuple[int, int]) -> str:
    """Map raw count to severity band. ``thresholds`` = (medium, high)."""
    if count >= thresholds[1]:
        return "high"
    if count >= thresholds[0]:
        return "medium"
    return "low"


def _sentences(text: str) -> list[str]:
    """Split into non-empty sentences by CJK punctuation."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _clean_for_prose_analysis(text: str) -> str:
    """Strip stage directions and scene headers before analyzing prose density.

    We only want to score the *narrative + dialog* body. Scene headers like
    ``【场景1】家·晚`` and action markers like ``△xxx`` are dropped so their
    filler-word usage doesn't dilute the signal.
    """
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("【场景") or stripped.startswith("△"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _find_offenders(text: str, needle: str, limit: int = 3) -> list[str]:
    """Return up to ``limit`` sentence fragments containing ``needle``."""
    hits: list[str] = []
    for sent in _sentences(text):
        if needle in sent:
            snippet = sent if len(sent) <= 40 else sent[:40] + "…"
            hits.append(snippet)
            if len(hits) >= limit:
                break
    return hits


def _detect_filler_words(text: str, text_len: int) -> dict[str, Any] | None:
    per_1000 = max(text_len / 1000.0, 0.001)
    heavy_hits: dict[str, int] = {}
    total = 0
    for word, threshold in FILLER_WORDS.items():
        count = text.count(word)
        if count == 0:
            continue
        # Normalize by text length; if density > threshold, this word is heavy
        density = count / per_1000
        if density >= threshold:
            heavy_hits[word] = count
        total += count

    if not heavy_hits and total < 5:
        return None

    # Severity: 3+ heavy words OR overall density > 20/1000 chars = high
    overall_density = total / per_1000
    if len(heavy_hits) >= 3 or overall_density >= 20:
        severity = "high"
    elif heavy_hits or overall_density >= 12:
        severity = "medium"
    else:
        severity = "low"

    examples: list[str] = []
    for w in heavy_hits:
        examples.extend(_find_offenders(text, w, limit=1))
        if len(examples) >= 3:
            break
    if not examples:
        # Fall back to any filler word we found
        for w in FILLER_WORDS:
            if text.count(w):
                examples.extend(_find_offenders(text, w, limit=1))
                if len(examples) >= 3:
                    break

    return {
        "type": "filler_word_overuse",
        "severity": severity,
        "count": total,
        "heavy_words": heavy_hits,
        "examples": examples[:3],
    }


def _detect_inner_monologue(text: str) -> dict[str, Any] | None:
    total = sum(text.count(m) for m in INNER_MONOLOGUE_MARKERS)
    if total == 0:
        return None

    severity = _severity_from_count(total, thresholds=(2, 5))
    if severity == "low" and total < 2:
        return None

    examples: list[str] = []
    for m in INNER_MONOLOGUE_MARKERS:
        examples.extend(_find_offenders(text, m, limit=1))
        if len(examples) >= 3:
            break

    return {
        "type": "inner_monologue_overuse",
        "severity": severity,
        "count": total,
        "examples": examples[:3],
    }


def _detect_sentence_uniformity(text: str) -> dict[str, Any] | None:
    sents = _sentences(text)
    if len(sents) < 6:
        return None

    lengths = [len(s) for s in sents]
    mean = statistics.mean(lengths)
    if mean == 0:
        return None
    try:
        stdev = statistics.pstdev(lengths)
    except statistics.StatisticsError:
        return None
    cv = stdev / mean  # coefficient of variation

    # Human drama typically CV ≥ 0.55 (mixes short punchy dialog with longer
    # action beats). CV < 0.35 = suspiciously uniform.
    if cv >= 0.5:
        return None
    if cv < 0.3:
        severity = "high"
    elif cv < 0.4:
        severity = "medium"
    else:
        severity = "low"

    return {
        "type": "sentence_rhythm_uniform",
        "severity": severity,
        "count": len(sents),
        "cv": round(cv, 3),
        "mean_length": round(mean, 1),
        "examples": [],
    }


def detect(text: str) -> dict[str, Any]:
    """Analyze ``text`` and return an ``AITellReport``.

    ``score`` starts at 100 and is docked by severity of each issue found:
        high   → −15
        medium → −10
        low    → −5
    """
    if not text or not text.strip():
        return {"score": 100, "sentence_count": 0, "issues": []}

    cleaned = _clean_for_prose_analysis(text)
    text_len = len(cleaned) or 1

    issues: list[dict[str, Any]] = []
    for detector in (
        _detect_filler_words(cleaned, text_len),
        _detect_inner_monologue(cleaned),
        _detect_sentence_uniformity(cleaned),
    ):
        if detector is not None:
            issues.append(detector)

    score = 100
    for iss in issues:
        deduct = {"high": 15, "medium": 10, "low": 5}.get(iss["severity"], 0)
        score -= deduct
    score = max(0, min(100, score))

    return {
        "score": score,
        "sentence_count": len(_sentences(cleaned)),
        "issues": issues,
    }


def issues_for_ralph(text: str) -> list[dict[str, Any]]:
    """Format detector issues so they slot into a Ralph review's ``issues`` list.

    Each item is shaped like the Review Agent's own issue schema (severity /
    type / description / suggestion) so downstream renderers don't branch.
    """
    report = detect(text)
    out: list[dict[str, Any]] = []
    for iss in report["issues"]:
        t = iss["type"]
        description = _describe(iss)
        suggestion = _suggest(iss)
        out.append({
            "severity": iss["severity"],
            "type": t,
            "description": description,
            "suggestion": suggestion,
            "detector_score": report["score"],
        })
    return out


def _describe(iss: dict[str, Any]) -> str:
    t = iss["type"]
    if t == "filler_word_overuse":
        heavies = ", ".join(iss.get("heavy_words", {}).keys()) or "多个"
        return f"叙述连词密度过高（{heavies} 等）总出现 {iss['count']} 次"
    if t == "inner_monologue_overuse":
        return f"内心独白标记出现 {iss['count']} 次（心想/暗想/内心 等）"
    if t == "sentence_rhythm_uniform":
        return f"句长过于均匀（CV={iss['cv']}），缺少短促对白与长动作交替"
    return iss.get("type", "")


def _suggest(iss: dict[str, Any]) -> str:
    t = iss["type"]
    if t == "filler_word_overuse":
        return "删掉一半以上的叙述连词；让镜头/动作/对白直接推进"
    if t == "inner_monologue_overuse":
        return "把内心独白改成外化行为或对白（show, don't tell）"
    if t == "sentence_rhythm_uniform":
        return "拆长句、砍短句节奏；对白 3-8 字 vs 动作 15-30 字交替"
    return ""
