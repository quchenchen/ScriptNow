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


def _scenario() -> GoldenScenario:
    return GoldenScenario.model_validate(
        {
            "schema_version": "creative-flow-golden/v1",
            "id": "test-flow",
            "domain": "novel",
            "workflow": "original",
            "description": "test",
            "stages": [
                {
                    "id": "write",
                    "required_artifacts": ["chapter_revision"],
                    "decision_required": True,
                }
            ],
        }
    )


def _observation(*, persisted: bool = True, operation_status: str = "succeeded"):
    return FlowObservation.model_validate(
        {
            "schema_version": "creative-flow-observation/v1",
            "scenario_id": "test-flow",
            "operation_id": "operation-1",
            "status": operation_status,
            "stages": [
                {
                    "id": "write",
                    "status": "succeeded",
                    "first_status_ms": 10,
                    "first_content_ms": 30,
                    "completed_ms": 80,
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "artifacts": [
                        {
                            "id": "artifact-1",
                            "kind": "chapter_revision",
                            "revision": "v1",
                            "readable": True,
                            "persisted": persisted,
                            "next_stage_consumable": True,
                        }
                    ],
                }
            ],
            "decisions": [
                {
                    "stage_id": "write",
                    "request_id": "decision-1",
                    "resolved": True,
                    "resolution_count": 1,
                }
            ],
        }
    )


def test_all_domain_golden_scenarios_validate():
    scenarios = [load_scenario(path) for path in sorted(GOLDEN_DIR.glob("*.json"))]

    assert {scenario.domain for scenario in scenarios} == {
        "novel",
        "script",
        "translation",
        "recreation",
    }


def test_success_requires_a_persisted_readable_consumable_artifact():
    report = audit_flow(_scenario(), _observation())

    assert report.passed is True
    assert report.completion_invariant_satisfied is True
    assert report.metrics.input_tokens == 100
    assert report.metrics.output_tokens == 200


def test_false_success_is_reported_when_artifact_is_not_persisted():
    report = audit_flow(_scenario(), _observation(persisted=False))

    assert report.passed is False
    assert [finding.code for finding in report.findings][:2] == [
        "false_success",
        "missing_consumable_artifact",
    ]


def test_decision_must_be_resolved_exactly_once():
    observation = _observation()
    observation.decisions[0].resolution_count = 2

    report = audit_flow(_scenario(), observation)

    assert report.passed is False
    assert any(
        finding.code == "decision_not_resolved_exactly_once"
        for finding in report.findings
    )


def test_duplicate_decision_does_not_hide_ambiguous_resolution():
    payload = _observation().model_dump(mode="json")
    payload["decisions"].append(
        {
            "stage_id": "write",
            "request_id": "decision-2",
            "resolved": False,
            "resolution_count": 0,
        }
    )
    observation = FlowObservation.model_validate(payload)

    report = audit_flow(_scenario(), observation)

    assert report.passed is False
    assert any(
        finding.code == "decision_not_resolved_exactly_once"
        for finding in report.findings
    )


@pytest.mark.parametrize(
    ("field", "duplicate"),
    [
        ("stages", {"id": "write", "status": "pending", "artifacts": []}),
        (
            "decisions",
            {
                "stage_id": "write",
                "request_id": "decision-1",
                "resolved": True,
                "resolution_count": 1,
            },
        ),
    ],
)
def test_observation_rejects_duplicate_evidence_keys(field, duplicate):
    payload = _observation().model_dump(mode="json")
    payload[field].append(duplicate)

    with pytest.raises(ValidationError):
        FlowObservation.model_validate(payload)


def test_scenario_rejects_undeclared_contract_fields():
    payload = _scenario().model_dump()
    payload["business_budget"] = "must come from the project contract"

    with pytest.raises(ValidationError):
        GoldenScenario.model_validate(payload)
