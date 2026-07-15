"""Split raw episode text into structured scene dicts.

Used by ``AgentTeam.save_episode`` when the writing agent produces a whole
episode as one blob — we split it before writing to the scenes table.

Format expected:
    【场景1】location·time
    △action lines...
    character：dialog...

    【场景2】...

If no markers are present, the whole text becomes a single scene #1.
"""
from __future__ import annotations

import re

_HEAD_RE = re.compile(r"^\s*【场景\s*(\d+)\s*】\s*(.*)$")


def split_scenes(content: str) -> list[dict]:
    """Return ``[{"scene_number", "location", "time", "content"}, ...]``.

    Numbers are dense (1..N) regardless of what appeared in the source.
    """
    if not content:
        return []

    current: dict | None = None
    scenes: list[dict] = []

    for line in content.split("\n"):
        m = _HEAD_RE.match(line)
        if m:
            if current is not None:
                scenes.append(current)
            rest = (m.group(2) or "").strip()
            if "·" in rest:
                loc, t = rest.split("·", 1)
                loc, t = loc.strip(), t.strip()
            else:
                loc, t = rest, ""
            current = {"location": loc, "time": t, "content_lines": []}
        else:
            if current is None:
                current = {"location": "", "time": "", "content_lines": [line]}
            else:
                current["content_lines"].append(line)

    if current is not None:
        scenes.append(current)

    if not scenes:
        return [{"scene_number": 1, "location": "", "time": "", "content": content.strip()}]

    return [
        {
            "scene_number": i,
            "location": s["location"],
            "time": s["time"],
            "content": "\n".join(s["content_lines"]).strip(),
        }
        for i, s in enumerate(scenes, start=1)
    ]
