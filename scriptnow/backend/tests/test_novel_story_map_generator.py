import json

import pytest

from scriptnow.novel.story_map_generator import (
    NovelStoryMapGenerationError,
    NovelStoryMapGenerator,
)


def test_story_map_preserves_user_owned_counts_and_word_target() -> None:
    payload = NovelStoryMapGenerator.parse(
        json.dumps(
            {
                "volumes": [
                    {
                        "title": "A Human Volume Title",
                        "chapters": [
                            {
                                "title": "A Human Chapter Title",
                                "point_of_view": "first person",
                                "beats": [
                                    {
                                        "objective": "The protagonist makes an irreversible choice.",
                                        "anchor_ids": ["plot:choice"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
    )

    volumes = NovelStoryMapGenerator.normalize(
        payload,
        volume_count=1,
        chapters_per_volume=1,
        target_words=1375,
        valid_anchor_ids={"plot:choice"},
    )

    assert volumes[0].chapters[0].target_words == 1375
    assert volumes[0].chapters[0].title == "A Human Chapter Title"
    assert volumes[0].chapters[0].beats[0].objective.endswith("choice.")


def test_story_map_rejects_agent_output_that_changes_user_chapter_count() -> None:
    payload = NovelStoryMapGenerator.parse(
        json.dumps(
            {
                "volumes": [
                    {
                        "title": "Volume",
                        "chapters": [
                            {
                                "title": "Only one",
                                "beats": [
                                    {
                                        "objective": "A consequential action changes the story.",
                                        "anchor_ids": ["plot:choice"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
    )

    with pytest.raises(NovelStoryMapGenerationError, match="requires 2"):
        NovelStoryMapGenerator.normalize(
            payload,
            volume_count=1,
            chapters_per_volume=2,
            target_words=1375,
            valid_anchor_ids={"plot:choice"},
        )
