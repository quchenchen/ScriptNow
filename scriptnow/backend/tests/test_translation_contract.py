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


def test_translation_rejects_changed_block_contract() -> None:
    original = TranslationUnit(
        titles={"chapter": "The Rejected Bond"},
        blocks=({"type": "prose", "text": "Rain followed her home."},),
    )

    with pytest.raises(TranslationError, match="block type contract"):
        FaithfulTranslationService._parse(
            '{"titles":{"chapter":"迟来的契约"},'
            '"blocks":[{"type":"quote","text":"雨一路跟她回家。"}]}',
            original=original,
        )
