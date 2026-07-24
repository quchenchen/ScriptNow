import pytest

from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.writer import NovelChapterGenerator, NovelWriterError


def test_writer_parses_structured_novel_blocks_without_internal_heading() -> None:
    blocks = NovelChapterGenerator.parse(
        '{"blocks":['
        '{"type":"heading","text":"The Silver Leaf"},'
        '{"type":"prose","text":"Sera turns the token over in her palm."},'
        '{"type":"dialogue","text":"Tell me who carried this."}'
        ']}',
        "run-123",
    )

    assert [block.type for block in blocks] == ["heading", "prose", "dialogue"]
    assert blocks[0].text == "The Silver Leaf"
    assert all("chapter-" not in block.text for block in blocks)


def test_writer_rejects_unstructured_or_headingless_output() -> None:
    with pytest.raises(NovelWriterError, match="章节结构不完整"):
        NovelChapterGenerator.parse(
            '{"blocks":[{"type":"prose","text":"Not a heading."}]}',
            "run-123",
        )


def test_writer_normalizes_provider_block_ids_content_and_epistolary_type() -> None:
    blocks = NovelChapterGenerator.parse(
        '{"blocks":['
        '{"id":"title","type":"heading","content":"The Rejected Bond"},'
        '{"id":"scene","type":"section","content":"Sera rides beyond the border."},'
        '{"id":"record","type":"epistolary","content":"Council record: the bond is rejected."}'
        ']}',
        "run-456",
    )

    assert [block.type for block in blocks] == ["heading", "prose", "quote"]
    assert blocks[2].text.startswith("Council record")


def test_writer_accepts_provider_blocks_as_root_array() -> None:
    blocks = NovelChapterGenerator.parse(
        '[{"type":"heading","content":"The Rejected Bond"},'
        '{"type":"paragraph","content":"Rain follows me down the mountain."},'
        '{"type":"paragraph","content":"The bond still burns beneath my ribs."}]',
        "run-root-array",
    )

    assert [block.type for block in blocks] == ["heading", "prose", "prose"]
    assert blocks[1].text == "Rain follows me down the mountain."


def test_writer_normalizes_provider_divider_caption_to_empty_text() -> None:
    blocks = NovelChapterGenerator.parse(
        '{"blocks":['
        '{"type":"heading","text":"The Rejected Bond"},'
        '{"type":"prose","text":"Sera leaves the throne room."},'
        '{"type":"divider","text":"***"},'
        '{"type":"prose","text":"Rain follows her into the pass."}'
        ']}',
        "run-divider",
    )

    assert [block.type for block in blocks] == ["heading", "prose", "divider", "prose"]
    assert blocks[2].text == ""


def test_writer_counts_english_words_for_hard_length_limit() -> None:
    blocks = (
        NovelBlock(block_id="h", type="heading", text="The Binding Throne"),
        NovelBlock(block_id="p", type="prose", text="The wolf's oath is broken."),
    )

    assert NovelChapterGenerator.count_manuscript_units(blocks, "en-US") == 8


def test_writer_splits_long_prose_into_lossless_readable_paragraphs() -> None:
    sentence = "Sera counts every coin before she answers the king."
    text = " ".join(sentence for _ in range(40))

    paragraphs = NovelChapterGenerator.split_readable_paragraphs(text, max_words=40)

    assert len(paragraphs) > 1
    assert " ".join(paragraphs) == text
    assert all(len(paragraph.split()) <= 40 for paragraph in paragraphs)


def test_writer_keeps_closing_quote_with_the_sentence() -> None:
    sentence = 'She said, "Someone will recognize it someday."'
    text = " ".join(sentence for _ in range(12))

    paragraphs = NovelChapterGenerator.split_readable_paragraphs(text, max_words=24)

    assert " ".join(paragraphs) == text
    assert all(not paragraph.startswith('"') for paragraph in paragraphs)


def test_writer_prompt_treats_source_revision_as_bounded_revision() -> None:
    class Project:
        direction = {"language": "en-US"}

    prompt = NovelChapterGenerator._prompt(
        Project(),
        {
            "creative_language": "en-US",
            "chapter": {"title": "The Binding Throne", "target_words": 1375},
            "source_revision": {
                "revision_id": "revision-3",
                "blocks": [{"type": "prose", "text": "Existing manuscript."}],
            },
        },
        "Condense to the target range.",
    )

    assert "bounded revision task" in prompt
    assert "do not restart from the premise" in prompt
    assert "Existing manuscript." in prompt
