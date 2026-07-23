import pytest
from pydantic import ValidationError

from scriptflow_v7.novel.contracts import NovelBlock
from scriptflow_v7.novel.revisions import NovelPatch
from scriptflow_v7.novel.story_map import Chapter, Volume
from scriptflow_v7.script.contracts import ScriptBlock
from scriptflow_v7.script.revisions import ScriptPatch
from scriptflow_v7.script.story_map import Episode, Scene


def test_script_story_map_uses_episode_scene_and_duration() -> None:
    episode = Episode(
        id="ep-1",
        ordinal=1,
        title="Opening",
        scenes=(Scene(id="sc-1", ordinal=1, title="Door", duration_seconds_target=90),),
    )

    assert episode.scenes[0].duration_seconds_target == 90
    assert "chapters" not in Episode.model_json_schema()["properties"]


def test_novel_story_map_uses_volume_chapter_words_and_pov() -> None:
    volume = Volume(
        id="vol-1",
        ordinal=1,
        title="Part One",
        chapters=(
            Chapter(
                id="ch-1",
                ordinal=1,
                title="Arrival",
                target_words=3000,
                point_of_view="Lin",
            ),
        ),
    )

    assert volume.chapters[0].target_words == 3000
    assert "scenes" not in Volume.model_json_schema()["properties"]


def test_script_patch_has_revision_and_exact_text_preconditions() -> None:
    patch = ScriptPatch(
        base_revision_id="rev-1",
        para_id="para-1",
        expected_text="Old",
        replacement=(ScriptBlock(para_id="para-2", type="action", text="New"),),
    )

    assert patch.para_id == "para-1"
    with pytest.raises(ValidationError):
        ScriptPatch(
            base_revision_id="rev-1",
            para_id="para-1",
            expected_text="Old",
            replacement=(),
        )


def test_novel_patch_cannot_accept_script_block() -> None:
    with pytest.raises(ValidationError):
        NovelPatch(
            base_revision_id="rev-1",
            block_id="block-1",
            expected_text="Old",
            replacement=(ScriptBlock(para_id="para-2", type="action", text="New"),),
        )

    patch = NovelPatch(
        base_revision_id="rev-1",
        block_id="block-1",
        expected_text="Old",
        replacement=(NovelBlock(block_id="block-2", type="prose", text="New"),),
    )
    assert patch.block_id == "block-1"
