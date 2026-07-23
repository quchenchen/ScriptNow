import json

import pytest

from scriptflow_v7.novel.blueprint import NovelBlueprintError, NovelBlueprintGenerator


def anchors() -> list[dict[str, object]]:
    kinds = [
        "world", "world", "character", "character", "character", "relationship",
        "relationship", "character_arc", "character_arc", "plot", "plot", "plot",
        "foreshadow", "foreshadow", "motif",
    ]
    return [
        {
            "id": f"{kind}:item-{index}",
            "kind": kind,
            "name": f"Blueprint item {index}",
            "payload": {"description": f"Actionable blueprint evidence and consequence {index}."},
        }
        for index, kind in enumerate(kinds, 1)
    ]


def test_parses_complete_novel_blueprint() -> None:
    payload = NovelBlueprintGenerator.parse(json.dumps({"anchors": anchors()}))

    assert len(payload.anchors) == 15
    assert {item.kind for item in payload.anchors} >= {"plot", "foreshadow", "relationship"}


def test_accepts_architect_envelope_metadata_without_persisting_it() -> None:
    payload = NovelBlueprintGenerator.parse(
        json.dumps(
            {
                "project_id": "project-1",
                "blueprint_title": "The Binding Throne",
                "structure": "three_act",
                "volumes": {"volume_1": {"title": "The Claim"}},
                "anchors": anchors(),
            }
        )
    )

    assert len(payload.anchors) == 15
    assert not hasattr(payload, "volumes")


def test_rejects_visually_full_but_structurally_incomplete_blueprint() -> None:
    incomplete = [item for item in anchors() if item["kind"] != "foreshadow"]

    with pytest.raises(NovelBlueprintError, match="missing foreshadow"):
        NovelBlueprintGenerator.parse(json.dumps({"anchors": incomplete}))
