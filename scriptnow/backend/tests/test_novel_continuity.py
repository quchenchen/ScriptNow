from types import SimpleNamespace

from scriptnow.novel.continuity import latest_effective_revisions


def revision(chapter_id: str, number: int, status: str, source: str = "agent"):
    return SimpleNamespace(
        chapter_id=chapter_id,
        revision_number=number,
        status=status,
        source=source,
    )


def test_latest_human_candidate_overrides_older_adopted_revision_for_continuity() -> None:
    adopted = revision("chapter-1", 1, "adopted")
    human = revision("chapter-1", 2, "candidate", "human")
    stale = revision("chapter-1", 3, "superseded")
    current_chapter = revision("chapter-2", 1, "candidate")

    selected = latest_effective_revisions(
        [adopted, human, stale, current_chapter],
        chapter_ids=["chapter-1", "chapter-2", "chapter-3"],
        before_chapter_id="chapter-2",
    )

    assert selected == [human]
