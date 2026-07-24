from collections.abc import Iterable, Sequence

from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus


def latest_effective_revisions(
    revisions: Iterable[NovelDocumentRevisionModel],
    *,
    chapter_ids: Sequence[str],
    before_chapter_id: str | None = None,
) -> list[NovelDocumentRevisionModel]:
    """Select the newest usable revision for each chapter in StoryMap order."""

    ordered_ids = list(chapter_ids)
    if before_chapter_id is not None:
        try:
            ordered_ids = ordered_ids[: ordered_ids.index(before_chapter_id)]
        except ValueError:
            return []

    allowed = {NovelRevisionStatus.CANDIDATE, NovelRevisionStatus.ADOPTED}
    latest_by_chapter: dict[str, NovelDocumentRevisionModel] = {}
    for revision in revisions:
        if revision.chapter_id not in ordered_ids or revision.status not in allowed:
            continue
        current = latest_by_chapter.get(revision.chapter_id)
        if current is None or revision.revision_number > current.revision_number:
            latest_by_chapter[revision.chapter_id] = revision

    return [latest_by_chapter[item] for item in ordered_ids if item in latest_by_chapter]
