import json
from types import SimpleNamespace

import pytest

from scriptnow.novel.ideation import NovelIdeationError, NovelIdeationGenerator


def candidate(index: int) -> dict[str, object]:
    return {
        "title": f"The Moonbound Choice {index}",
        "premise": (
            f"Direction {index}: An exiled wolf heir must choose between breaking a blood bond "
            "and protecting the rival whose memories now bleed into hers, while their clans turn "
            "the approaching eclipse into a war that will cost one of them a name and a future."
        ),
        "point_of_view": "Close third person, alternating",
        "narrative_constraints": ["No coerced love", "Every magical cost remains visible"],
        "angles": [
            f"protagonist desire: freedom {index}",
            f"opposing force: clan law {index}",
            f"emotional promise: earned trust {index}",
            f"moral dilemma: love or autonomy {index}",
            f"ending cost: irreversible loss {index}",
        ],
    }


def test_parses_exactly_three_distinct_structured_directions() -> None:
    payload = NovelIdeationGenerator.parse(
        json.dumps({"candidates": [candidate(1), candidate(2), candidate(3)]})
    )

    assert len(payload.candidates) == 3
    assert payload.candidates[0].title == "The Moonbound Choice 1"


def test_rejects_template_directions_that_only_repeat_the_same_content() -> None:
    repeated = candidate(1)

    with pytest.raises(NovelIdeationError, match="genuinely distinct"):
        NovelIdeationGenerator.parse(
            json.dumps({"candidates": [repeated, repeated, repeated]})
        )


def test_repairs_truncated_json_before_validating_candidates() -> None:
    text = json.dumps({"candidates": [candidate(1), candidate(2), candidate(3)]})

    payload = NovelIdeationGenerator.parse(text[:-1])

    assert len(payload.candidates) == 3


def test_initial_rag_plan_uses_project_and_writer_feedback_without_model_call() -> None:
    project = SimpleNamespace(
        direction={
            "genre": "werewolf, dark romance",
            "premise": "rejection is protection; the bond is constitutional power",
        }
    )

    plan = NovelIdeationGenerator._initial_retrieval_plan(  # noqa: SLF001
        project,
        "compare political legitimacy with intimate betrayal",
    )

    assert plan.sufficient is False
    assert any("constitutional" in query for query in plan.queries)
    assert any("betrayal" in query for query in plan.queries)


def test_parses_iterative_rag_plan_and_ranks_matching_source_chunks() -> None:
    plan = NovelIdeationGenerator.parse_retrieval_plan(
        json.dumps(
            {
                "queries": ["Lyra blood bond", "rival pack law", "eclipse ending cost"],
                "coverage_gaps": ["antagonist motive"],
                "sufficient": False,
            }
        )
    )

    assert plan.queries[0] == "Lyra blood bond"
    assert plan.coverage_gaps == ("antagonist motive",)


def test_parses_rag_plan_when_runtime_explains_before_json_fence() -> None:
    plan = NovelIdeationGenerator.parse_retrieval_plan(
        "Evidence coverage analysis.\n"
        "```json\n"
        '{"queries":["Lyra origin","blood bond rules","eclipse ending"],'
        '"coverage_gaps":[],"sufficient":true}'
        "\n```"
    )

    assert plan.sufficient is True
    assert plan.queries[2] == "eclipse ending"


def test_caps_rag_plan_to_iteration_budget() -> None:
    plan = NovelIdeationGenerator.parse_retrieval_plan(
        json.dumps(
            {
                "queries": [f"source query {index}" for index in range(36)],
                "coverage_gaps": [f"gap {index}" for index in range(34)],
                "sufficient": False,
            }
        )
    )

    assert len(plan.queries) == 32
    assert len(plan.coverage_gaps) == 32
