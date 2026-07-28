from pathlib import Path

import pytest
from pydantic import ValidationError

from scriptnow.platform.creative_flow_audit import (
    FlowObservation,
    GoldenScenario,
    audit_flow,
    load_scenario,
)

GOLDEN_DIR = Path(__file__).parents[1] / "golden" / "creative-flow-v1"


def _successful_observation(scenario: GoldenScenario) -> FlowObservation:
    stages = []
    decisions = []
    for stage_index, stage in enumerate(scenario.stages, start=1):
        stages.append(
            {
                "id": stage.id,
                "status": "succeeded",
                "first_status_ms": stage_index * 10,
                "first_content_ms": stage_index * 20,
                "completed_ms": stage_index * 100,
                "input_tokens": stage_index,
                "output_tokens": stage_index * 2,
                "artifacts": [
                    {
                        "id": f"{scenario.domain}-{stage.id}-{artifact_index}",
                        "kind": artifact_kind,
                        "revision": "fixture-v1",
                        "readable": True,
                        "persisted": True,
                        "next_stage_consumable": True,
                    }
                    for artifact_index, artifact_kind in enumerate(
                        stage.required_artifacts,
                        start=1,
                    )
                ],
            }
        )
        if stage.decision_required:
            decisions.append(
                {
                    "stage_id": stage.id,
                    "request_id": f"{scenario.id}:{stage.id}:decision",
                    "resolved": True,
                    "resolution_count": 1,
                }
            )
    return FlowObservation.model_validate(
        {
            "schema_version": "creative-flow-observation/v1",
            "scenario_id": scenario.id,
            "operation_id": f"fixture:{scenario.id}",
            "status": "succeeded",
            "stages": stages,
            "decisions": decisions,
        }
    )


@pytest.mark.parametrize(
    "scenario_name",
    [
        "novel-original",
        "script-original",
        "faithful-translation",
        "cross-cultural-recreation",
    ],
)
def test_sanitized_four_domain_fixture_satisfies_its_golden_contract(
    scenario_name: str,
) -> None:
    scenario = load_scenario(GOLDEN_DIR / f"{scenario_name}.json")

    report = audit_flow(scenario, _successful_observation(scenario))

    assert report.passed is True
    assert report.completion_invariant_satisfied is True


@pytest.mark.parametrize(
    ("operation_status", "stage_status", "error_category"),
    [
        ("failed", "failed", "timeout"),
        ("cancelled", "cancelled", "cancellation"),
        ("partial", "partial", "recovery"),
    ],
)
def test_fault_observation_cannot_be_published_as_success(
    operation_status: str,
    stage_status: str,
    error_category: str,
) -> None:
    scenario = load_scenario(GOLDEN_DIR / "novel-original.json")
    payload = _successful_observation(scenario).model_dump(mode="json")
    payload["status"] = operation_status
    payload["stages"][0]["status"] = stage_status
    payload["stages"][0]["error_category"] = error_category

    report = audit_flow(scenario, FlowObservation.model_validate(payload))

    assert report.passed is False
    assert any(
        finding.code == "stage_not_succeeded" and finding.stage_id == "ideation"
        for finding in report.findings
    )


def test_refresh_cannot_duplicate_a_stage_or_decision_identity() -> None:
    scenario = load_scenario(GOLDEN_DIR / "script-original.json")
    payload = _successful_observation(scenario).model_dump(mode="json")
    payload["stages"].append(payload["stages"][0])

    with pytest.raises(ValidationError, match="observed stage ids must be unique"):
        FlowObservation.model_validate(payload)

    payload = _successful_observation(scenario).model_dump(mode="json")
    payload["decisions"].append(payload["decisions"][0])
    with pytest.raises(ValidationError, match="decision request ids must be unique"):
        FlowObservation.model_validate(payload)
