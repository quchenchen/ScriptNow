"""Pre-computed context helpers for the Novel Writer.

These functions build compact text summaries from database data BEFORE
the prompt is assembled, avoiding the need for Agent tool calls (which
DeepSeek v4-pro does not reliably support).
"""


async def build_review_highlights(database, project_id: str, current_chapter_id: str) -> str:
    """Fetch blocking/major findings from the last quality report for the prior chapter.

    Returns compact text suitable for injection into Writer's prompt as
    "⚠️ 注意事项" (Watch Out For).
    """
    from sqlalchemy import desc
    from sqlalchemy import select as sa_select

    from scriptnow.novel.domain import NovelQualityReportModel

    async with database.session() as session:
        reports = list(
            await session.scalars(
                sa_select(NovelQualityReportModel)
                .where(NovelQualityReportModel.project_id == project_id)
                .order_by(desc(NovelQualityReportModel.created_at))
                .limit(1)
            )
        )
    if not reports:
        return ""

    report = reports[0]
    dims = report.dimensions or []
    blocking = [d for d in dims if d.get("verdict") in ("blocking", "major")]
    if not blocking:
        return ""

    lines = ["## ⚠️ Review Findings (Watch Out For)"]
    for d in blocking:
        verdict = d.get("verdict", "?")
        dimension = d.get("dimension", "?")
        summary = d.get("summary", "")[:200]
        lines.append(f"- [{verdict}] {dimension}: {summary}")
    return "\n".join(lines)



def build_prior_summary(revisions, current_chapter_id: str) -> str:
    """Compact summary of prior chapters — last 6, ~500 chars each."""
    prior = [r for r in revisions if r.chapter_id != current_chapter_id]
    if not prior:
        return "This is the first chapter."
    lines = ["## Prior Chapters Summary"]
    for rev in sorted(prior, key=lambda r: r.chapter_id)[-6:]:
        blocks = [b for b in rev.blocks if b]
        if not blocks:
            continue
        title = rev.chapter_id
        for b in blocks[:5]:
            if hasattr(b, "type") and b.type == "heading":
                title = str(getattr(b, "text", rev.chapter_id))
                break
        snippet = " ".join(
            str(getattr(b, "text", ""))[:200]
            for b in blocks[-10:]
            if hasattr(b, "type") and b.type in ("prose", "dialogue")
        )
        lines.append(f"- **{rev.chapter_id} ({title})**: {snippet[:400]}")
    return "\n".join(lines)


async def build_character_graph(database, project_id: str, current_chapter_id: str) -> str:
    """Compact character profiles + chapter summaries from creative graph."""
    try:
        from scriptnow.novel.creative_graph import read_creative_graph

        data = await read_creative_graph(database, project_id=project_id, compact=True)
    except Exception:
        return ""

    nodes = data.get("nodes", [])
    chapters = data.get("chapters", [])
    prior_chapters = [
        c for c in chapters
        if str(c.get("chapter_key", c.get("id", ""))).replace("chapter:", "") != current_chapter_id
    ]

    lines = ["## Story So Far"]
    for ch in prior_chapters[-6:]:
        cid = str(ch.get("chapter_key", ch.get("id", ""))).replace("chapter:", "")
        label = ch.get("label", ch.get("title", "untitled"))
        summary = (ch.get("summary", "") or "")[:200]
        lines.append(f"- [{cid}] **{label}**: {summary}")

    characters = [n for n in nodes if n.get("type") == "character"]
    if characters:
        lines.append("\n### Characters")
        for n in characters:
            name = n.get("label", n.get("name", "?"))
            ntype = n.get("type", "")
            attrs = dict(n.get("attributes") or {})
            attr_text = " · ".join(f"{k}:{v}" for k, v in attrs.items() if str(v).strip())
            suffix = f" — {attr_text}" if attr_text else ""
            lines.append(f"- **{name}** [{ntype}]{suffix}")

    locations = [n for n in nodes if n.get("type") == "location"][:5]
    if locations:
        lines.append("\n### Locations")
        for n in locations:
            name = n.get("label", n.get("name", "?"))
            lines.append(f"- **{name}**")

    return "\n".join(lines)


async def build_narrative_state(project_id: str, prior_revisions) -> str:
    """Build cumulative narrative state: hooks, traits, events.

    This is Layer 2-3 of the progressive disclosure system.
    For previously generated chapters, extracts and caches exit notes.
    """
    from scriptnow.novel.narrative_extractor import (
        extract_chapter_exit_note,
        get_narrative_state,
        update_narrative_state,
    )

    state = get_narrative_state(project_id)
    # Ensure all prior chapters have exit notes
    for rev in prior_revisions:
        existing = [c for c in state.chapters if c.chapter_id == rev.chapter_id]
        if not existing:
            # Extract exit note from the revision blocks
            blocks = [b for b in rev.blocks if b]
            chapter_text = " ".join(
                str(getattr(b, "text", "")) for b in blocks
                if hasattr(b, "type") and b.type in ("prose", "dialogue")
            )
            if chapter_text.strip():
                word_count = len(chapter_text.split())
                note = extract_chapter_exit_note(
                    chapter_id=rev.chapter_id,
                    chapter_text=chapter_text,
                    word_count=word_count,
                )
                update_narrative_state(project_id, note)

    # Return compact state
    compact = state.to_markdown(compact=True)
    if compact:
        return compact

    # Fallback: return the full state
    return state.to_markdown(compact=False)
