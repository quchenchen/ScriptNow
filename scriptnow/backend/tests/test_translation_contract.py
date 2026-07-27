import pytest

from scriptnow.platform.translation import FaithfulTranslationService, TranslationError
from scriptnow.platform.translation_contracts import TranslationUnit


def test_translation_rejects_unstructured_provider_output() -> None:
    original = TranslationUnit(
        titles={"chapter": "The Rejected Bond"},
        blocks=({"type": "prose", "text": "Rain followed her home."},),
    )

    with pytest.raises(TranslationError, match="invalid structured response"):
        FaithfulTranslationService._parse(
            "Rain followed her home.",
            original=original,
        )


def test_translation_rejects_changed_block_count() -> None:
    original = TranslationUnit(
        titles={"chapter": "The Rejected Bond"},
        blocks=({"type": "prose", "text": "Rain followed her home."},),
    )

    with pytest.raises(TranslationError, match="block count"):
        FaithfulTranslationService._parse(
            '{"titles":["迟来的契约"],"blocks":[]}',
            original=original,
        )


def test_translation_reassembles_text_without_round_tripping_structure() -> None:
    original = TranslationUnit(
        titles={"chapter": "The Rejected Bond"},
        blocks=(
            {
                "block_id": "p-1",
                "type": "prose",
                "text": "Rain followed her home.",
                "revision_note": "keep",
            },
        ),
    )

    translated = FaithfulTranslationService._parse(
        '{"titles":["迟来的契约"],"blocks":["雨一路跟她回家。"]}',
        original=original,
    )

    assert translated.titles == {"chapter": "迟来的契约"}
    assert translated.blocks == (
        {
            "block_id": "p-1",
            "type": "prose",
            "text": "雨一路跟她回家。",
            "revision_note": "keep",
        },
    )
