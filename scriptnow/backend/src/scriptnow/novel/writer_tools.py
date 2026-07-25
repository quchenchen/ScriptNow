"""AgentScope tools for the Writer agent — deterministic database queries.

These tools replace the bulk JSON context passed to the Writer prompt,
reducing context size from ~90K chars to ~8K chars while providing
more precise, on-demand access to prior chapters, creative graph data,
quality reports, and blueprint anchors.
"""

from scriptnow.novel.creative_graph import read_creative_graph
from scriptnow.platform.database import Database

# ── Tool function signatures (AgentScope-compatible docstrings) ──────────


async def get_prior_chapter_summaries(
    database: Database,
    *,
    project_id: str,
    max_chapters: int = 6,
) -> str:
    """Return condensed summaries of the most recently written chapters.

    Use this before drafting to understand what happened in the story so far.
    Each summary includes the chapter title and a 1-2 sentence synopsis.

    Args:
        project_id: The project UUID.
        max_chapters: Maximum number of prior chapter summaries to return (default 6).

    Returns:
        A markdown-formatted string with chapter summaries, newest first.
    """
    data = await read_creative_graph(database, project_id=project_id)
    chapters = data.get("chapters", [])
    recent = chapters[-max_chapters:]
    if not recent:
        return "No prior chapter summaries available."

    lines = ["## Prior Chapter Summaries\n"]
    for ch in reversed(recent):
        lines.append(f"- **{ch.get('label', ch.get('title', 'untitled'))}**")
    return "\n".join(lines)


async def get_creative_graph_entities(
    database: Database,
    *,
    project_id: str,
    entity_types: str | None = None,
    max_nodes: int = 20,
) -> str:
    """Query the creative graph for characters, locations, objects, events, or concepts.

    Use this to verify character names, faction affiliations, locations,
    or any established entity from prior chapters before writing new content.

    Args:
        project_id: The project UUID.
        entity_types: Comma-separated list of types to filter by
            (e.g., "character,location,event"). If omitted, returns all types.
        max_nodes: Maximum number of nodes to return (default 20).

    Returns:
        A markdown-formatted list of matching entities with descriptions.
    """
    data = await read_creative_graph(database, project_id=project_id)
    nodes = data.get("nodes", [])
    if entity_types:
        allowed = {t.strip() for t in entity_types.split(",")}
        nodes = [n for n in nodes if n.get("type") in allowed]
    nodes = nodes[:max_nodes]

    if not nodes:
        return "No matching entities found in the creative graph."

    lines = ["## Creative Graph Entities\n"]
    for n in nodes:
        summary = (n.get("summary") or n.get("description") or "")[:200]
        aliases_str = ""
        if n.get("aliases"):
            aliases_str = f" (aka {', '.join(n['aliases'][:4])})"
        lines.append(f"- **[{n.get('type', 'unknown')}] {n.get('label', n.get('name', '?'))}**{aliases_str}: {summary}")
    return "\n".join(lines)


async def get_last_quality_report(
    database: Database,
    *,
    project_id: str,
    chapter_id: str,
) -> str:
    """Get the latest quality review for a chapter.

    Use this before revising or before writing the next chapter to avoid
    repeating errors caught by the reviewer.

    Args:
        project_id: The project UUID.
        chapter_id: The chapter identifier (e.g., "chapter-3-1").

    Returns:
        A summary of the reviewer's findings, or a message that no report exists.
    """
    from sqlalchemy import desc
    from sqlalchemy import select as sa_select

    from scriptnow.platform.models import NovelQualityReportModel

    async with database.session() as session:
        reports = list(
            await session.scalars(
                sa_select(NovelQualityReportModel)
                .where(
                    NovelQualityReportModel.project_id == project_id,
                    NovelQualityReportModel.chapter_id == chapter_id,
                )
                .order_by(desc(NovelQualityReportModel.created_at))
                .limit(1)
            )
        )

    if not reports:
        return f"No quality report available for {chapter_id}."

    report = reports[0]
    dims = ""
    for d in (report.dimensions or []):
        dims += f"- **{d.get('dimension', '?')}**: {d.get('verdict', '?')} — {d.get('summary', '')[:200]}\n"
    return f"## Last Quality Report for {chapter_id}\n{dims or 'No dimension details available.'}\nOverall: {report.overall_status or 'unknown'}"


async def get_chapter_beat(
    database: Database,
    *,
    project_id: str,
    chapter_id: str,
) -> str:
    """Get the StoryMap beat for a specific chapter.

    Use this to retrieve the planned outline for the chapter you are about to write.

    Args:
        project_id: The project UUID.
        chapter_id: The chapter identifier (e.g., "chapter-4-1").

    Returns:
        The chapter title and beat description from the adopted StoryMap.
    """
    from sqlalchemy import select as sa_select

    from scriptnow.novel.domain import NovelStoryMapModel

    async with database.session() as session:
        story_map = (
            await session.scalars(
                sa_select(NovelStoryMapModel).where(
                    NovelStoryMapModel.project_id == project_id,
                )
            )
        ).one_or_none()

    if story_map is None:
        return "No adopted StoryMap found."

    for vol in story_map.volumes:
        for ch in vol.get("chapters", []):
            if str(ch.get("id")) == chapter_id:
                title = ch.get("title", "untitled")
                beat = ch.get("beat", "")
                return f"## Chapter Beat: {title}\n{beat}"

    return f"Chapter {chapter_id} not found in StoryMap."


# ── Tool registry ─────────────────────────────────────────────────

# Map of tool name → handler function for the Writer toolkit
WRITER_TOOLS: dict[str, callable] = {
    "get_prior_chapter_summaries": get_prior_chapter_summaries,
    "get_creative_graph_entities": get_creative_graph_entities,
    "get_last_quality_report": get_last_quality_report,
    "get_chapter_beat": get_chapter_beat,
}

# ── Toolkit factory ───────────────────────────────────────────────

def create_writer_toolkit(database: Database) -> list:
    """Create AgentScope FunctionTool instances for the Writer agent.

    Returns a list of ToolBase objects that can be passed to
    Toolkit(tools=...).
    """
    from functools import partial

    from agentscope.tool import FunctionTool

    return [
        FunctionTool(
            partial(get_prior_chapter_summaries, database),
            name="get_prior_chapter_summaries",
            description="Get condensed summaries of the most recently written chapters. Use before drafting to understand prior events.",
        ),
        FunctionTool(
            partial(get_creative_graph_entities, database),
            name="get_creative_graph_entities",
            description="Query the creative graph for characters, locations, objects, events, or concepts established in prior chapters. Filter by type.",
        ),
        FunctionTool(
            partial(get_last_quality_report, database),
            name="get_last_quality_report",
            description="Get the latest quality review report for a specific chapter. Use to avoid repeating errors caught by the reviewer.",
        ),
        FunctionTool(
            partial(get_chapter_beat, database),
            name="get_chapter_beat",
            description="Get the planned StoryMap beat/outline for a specific chapter. Use before drafting to know what to write.",
        ),
    ]
