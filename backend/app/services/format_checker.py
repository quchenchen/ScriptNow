"""Script format checker — catches malformed scenes / stray markdown / bad dialog.

Not a linter for prose (that's the AI-tell detector). This one enforces the
script-sheet contract:

- Every scene starts with a ``【场景N】location·time`` heading
- Action lines start with ``△``
- Dialog is ``角色名：内容`` (Chinese full-width colon)
- No markdown residue (**bold**, `code`, ``` fences, > blockquotes)
- No stray "对白：" / "旁白：" placeholders left in
- No double-blank runs of more than 2 empty lines

Emits Issue dicts shaped to slot into the Ralph loop's issue list.
"""
from __future__ import annotations

import re
from typing import Any

# Scene heading: 【场景N】... — required at the top of every scene block
_SCENE_HEAD = re.compile(r"^\s*【场景\s*(\d+)\s*】\s*(.+)$")
# Action line: starts with △
_ACTION = re.compile(r"^\s*△")
# Dialog: `角色名：xxxx` (full-width colon). Half-width `:` is a common
# LLM mistake — flag it.
_DIALOG_FULL = re.compile(r"^\s*([^\s：:]{1,10})：(.+)$")
_DIALOG_HALF = re.compile(r"^\s*([^\s：:]{1,10}):(.+)$")

# Markdown residue patterns
_MD_BOLD = re.compile(r"\*\*[^*\n]+\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*[^*\n]+\*(?!\*)")
_MD_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MD_FENCE = re.compile(r"^```")
_MD_HEADING = re.compile(r"^#{1,6}\s+")
_MD_BULLET = re.compile(r"^\s*[-*+]\s+")


def _mk_issue(severity: str, type_: str, description: str, suggestion: str,
              location: str = "", examples: list[str] | None = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "type": type_,
        "description": description,
        "suggestion": suggestion,
        "location": location,
        "examples": examples or [],
    }


def check(text: str) -> dict[str, Any]:
    """Return ``{"score": int, "issues": [...]}``.

    Score starts at 100. Each issue subtracts by severity:
        high   → 15
        medium → 10
        low    → 5
    """
    if not text or not text.strip():
        return {"score": 100, "issues": []}

    issues: list[dict[str, Any]] = []
    lines = text.split("\n")

    # ── Markdown residue ────────────────────────────────────────
    md_examples: list[str] = []
    for i, line in enumerate(lines, start=1):
        if _MD_FENCE.match(line):
            md_examples.append(f"L{i}: ``` fence")
        elif _MD_HEADING.match(line):
            md_examples.append(f"L{i}: {line[:30]}")
    for pattern, label in (
        (_MD_BOLD, "**bold**"),
        (_MD_INLINE_CODE, "`code`"),
    ):
        for m in pattern.finditer(text):
            md_examples.append(f"{label}: {m.group(0)[:20]}")
            if len(md_examples) >= 5:
                break
    if md_examples:
        issues.append(_mk_issue(
            severity="high",
            type_="markdown_residue",
            description="剧本正文里混入了 markdown 语法",
            suggestion="去掉 **粗体** / `代码` / # 标题 / ``` 代码块 / 项目符号",
            examples=md_examples[:3],
        ))

    # ── Scene structure ─────────────────────────────────────────
    # Find heading positions; text between heads should have at least one △
    # action or dialog line to count as a valid scene body.
    heads: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _SCENE_HEAD.match(line)
        if m:
            heads.append((i, line.strip()))

    if not heads:
        # Non-empty text without any scene head is malformed
        issues.append(_mk_issue(
            severity="high",
            type_="missing_scene_heading",
            description="剧本没有任何 【场景N】 标记",
            suggestion="每个场景以 【场景N】地点·时间 开头",
        ))
    else:
        # Check heading format contains location·time
        bad_heads: list[str] = []
        for _idx, head in heads:
            m = _SCENE_HEAD.match(head)
            rest = (m.group(2) if m else "").strip()
            # Expect at least location; time is optional but preferred
            if not rest:
                bad_heads.append(head)
            elif "·" not in rest and " " not in rest:
                # No separator between location & time — allow just location
                # (some scenes are location-only), just don't require time.
                pass
        if bad_heads:
            issues.append(_mk_issue(
                severity="medium",
                type_="malformed_scene_heading",
                description="场景标题缺少地点信息",
                suggestion="【场景N】必须紧跟地点，形如 【场景1】咖啡馆·白天",
                examples=bad_heads[:3],
            ))

    # ── Half-width colon in dialog ──────────────────────────────
    half_examples: list[str] = []
    for i, line in enumerate(lines, start=1):
        # Skip lines that already parse as full-width dialog or actions
        if _ACTION.match(line) or _SCENE_HEAD.match(line):
            continue
        if _DIALOG_FULL.match(line):
            continue
        m = _DIALOG_HALF.match(line)
        if m:
            half_examples.append(f"L{i}: {line.strip()[:30]}")
            if len(half_examples) >= 3:
                break
    if half_examples:
        issues.append(_mk_issue(
            severity="medium",
            type_="dialog_half_width_colon",
            description="对白用了半角冒号 :，应改为全角 ：",
            suggestion="角色名和对白之间用中文全角冒号：",
            examples=half_examples,
        ))

    # ── Placeholder strings ────────────────────────────────────
    placeholder_examples: list[str] = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped in ("对白：", "旁白：", "台词：", "动作：", "对话：") or \
           stripped.startswith(("对白：", "旁白：", "台词：", "动作：")) and \
           len(stripped) < 6:
            placeholder_examples.append(f"L{i}: {stripped}")
    if placeholder_examples:
        issues.append(_mk_issue(
            severity="high",
            type_="placeholder_left_in",
            description="剧本里残留了模板占位符（对白：/ 旁白：等）",
            suggestion="删除占位符或补齐内容",
            examples=placeholder_examples[:3],
        ))

    # ── Excessive blank runs ────────────────────────────────────
    blank_run = 0
    max_blank = 0
    for line in lines:
        if not line.strip():
            blank_run += 1
            max_blank = max(max_blank, blank_run)
        else:
            blank_run = 0
    if max_blank > 3:
        issues.append(_mk_issue(
            severity="low",
            type_="excessive_blank_lines",
            description=f"连续空行超过 3 行（{max_blank} 行）",
            suggestion="场景之间用 1 空行分隔即可",
        ))

    # ── Score ──────────────────────────────────────────────────
    score = 100
    for iss in issues:
        score -= {"high": 15, "medium": 10, "low": 5}.get(iss["severity"], 0)
    score = max(0, min(100, score))

    return {"score": score, "issues": issues}


def issues_for_ralph(text: str) -> list[dict[str, Any]]:
    """Return format issues shaped like Ralph review issues."""
    return check(text)["issues"]
