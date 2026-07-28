import json
from pathlib import Path

import pytest

from scriptnow.platform.skill_benchmarks import (
    SkillBenchmarkError,
    SkillTrialResult,
    evaluate_skill_trials,
    load_benchmark_suite,
    record_skill_admission,
)
from scriptnow.platform.skills import CreativeProfile, SkillCatalog, SkillResolver

SKILLS_ROOT = Path(__file__).parents[1] / "skills"
BENCHMARK_ROOT = SKILLS_ROOT / "benchmarks"


def _paired_trials(*, baseline_score: float, candidate_score: float) -> list[SkillTrialResult]:
    suite = load_benchmark_suite(BENCHMARK_ROOT / "novel-genre-benchmark-v2.json")
    trials: list[SkillTrialResult] = []
    for case in suite.cases:
        for variant, score in (
            ("baseline", baseline_score),
            ("candidate", candidate_score),
        ):
            trials.append(
                SkillTrialResult(
                    case_key=case.key,
                    variant=variant,
                    anchor_scores={key: score for key in case.anchor_keys},
                    input_tokens=1000,
                    output_tokens=1000,
                    latency_ms=100,
                    evaluator="test-rubric-v1",
                    evidence=[f"{case.key}:{variant}"],
                )
            )
    return trials


def test_genre_benchmark_suite_has_broad_quality_and_market_coverage() -> None:
    suite = load_benchmark_suite(BENCHMARK_ROOT / "novel-genre-benchmark-v2.json")

    assert len(suite.anchors) == 9
    assert len(suite.cases) >= 12
    assert {case.language for case in suite.cases} == {"zh-CN", "en-US"}
    assert {"director", "architect", "writer", "reviewer"} <= {
        case.role for case in suite.cases
    }


def test_paired_benchmark_reports_measured_lift_and_gate_result() -> None:
    suite = load_benchmark_suite(BENCHMARK_ROOT / "novel-genre-benchmark-v2.json")

    passed = evaluate_skill_trials(
        suite=suite,
        candidate_skill_digest="candidate-v2",
        trials=_paired_trials(baseline_score=65, candidate_score=78),
    )
    failed = evaluate_skill_trials(
        suite=suite,
        candidate_skill_digest="candidate-regression",
        trials=_paired_trials(baseline_score=75, candidate_score=70),
    )

    assert passed.passed is True
    assert passed.lift == 13
    assert failed.passed is False
    assert "minimum_candidate_score" in failed.failed_gates
    assert "minimum_lift" in failed.failed_gates
    assert len(failed.regressed_anchors) == 9


def test_benchmark_rejects_incomplete_or_unpaired_evidence() -> None:
    suite = load_benchmark_suite(BENCHMARK_ROOT / "novel-genre-benchmark-v2.json")
    trials = _paired_trials(baseline_score=60, candidate_score=80)
    trials.pop()

    with pytest.raises(SkillBenchmarkError, match="paired trials"):
        evaluate_skill_trials(
            suite=suite,
            candidate_skill_digest="candidate-v2",
            trials=trials,
        )


def test_admission_registry_is_updated_from_measured_report(tmp_path: Path) -> None:
    suite = load_benchmark_suite(BENCHMARK_ROOT / "novel-genre-benchmark-v2.json")
    registry = tmp_path / "admission.json"
    registry.write_text(
        json.dumps(
            {
                "domains": {
                    "novel": {
                        "candidate": {
                            "status": "candidate",
                            "quality_status": "baseline_required",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    report = evaluate_skill_trials(
        suite=suite,
        candidate_skill_digest="digest-v2",
        trials=_paired_trials(baseline_score=65, candidate_score=78),
    )

    decision = record_skill_admission(
        registry_path=registry,
        domain="novel",
        skill_name="candidate",
        report=report,
        report_path="reports/candidate-v2.json",
    )

    stored = json.loads(registry.read_text(encoding="utf-8"))["domains"]["novel"]["candidate"]
    assert decision.status == "admitted"
    assert stored["quality_status"] == "measured"
    assert stored["candidate_digest"] == "digest-v2"
    assert stored["benchmark_report"] == "reports/candidate-v2.json"


def test_failed_quality_report_quarantines_candidate(tmp_path: Path) -> None:
    suite = load_benchmark_suite(BENCHMARK_ROOT / "novel-genre-benchmark-v2.json")
    registry = tmp_path / "admission.json"
    registry.write_text(
        '{"domains":{"novel":{"candidate":{"status":"candidate"}}}}',
        encoding="utf-8",
    )
    report = evaluate_skill_trials(
        suite=suite,
        candidate_skill_digest="regression",
        trials=_paired_trials(baseline_score=80, candidate_score=60),
    )

    decision = record_skill_admission(
        registry_path=registry,
        domain="novel",
        skill_name="candidate",
        report=report,
        report_path="reports/rejected.json",
    )

    assert decision.status == "quarantined"
    assert (
        json.loads(registry.read_text(encoding="utf-8"))["domains"]["novel"]["candidate"][
            "quality_status"
        ]
        == "rejected"
    )


def test_external_category_map_has_37_independently_owned_capabilities() -> None:
    value = json.loads(
        (BENCHMARK_ROOT / "novel-genre-capability-map-v1.json").read_text(encoding="utf-8")
    )
    categories = value["categories"]
    catalog_names = {item.name for item in SkillCatalog(SKILLS_ROOT).scan()}

    assert len(categories) == 37
    assert len({item["source_label"] for item in categories}) == 37
    assert len({item["canonical"] for item in categories}) == 37
    assert {item["owner"] for item in categories} <= catalog_names


def test_new_genre_capabilities_separate_routing_from_quality_evidence() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    names = {
        "novel-cn-commercial-emotion",
        "novel-cn-concept-short",
        "novel-cn-history-society",
        "novel-cn-profession-live",
    }
    skills = {item.name: item for item in catalog.scan() if item.name in names}

    assert set(skills) == names
    assert all(item.admission_status == "admitted" for item in skills.values())
    assert all(item.quality_status == "baseline_required" for item in skills.values())
    assert all(item.benchmark_suite == "novel-genre-benchmark-v2" for item in skills.values())


@pytest.mark.parametrize(
    ("genre", "expected_skill"),
    [
        ("狗血言情, 职场婚恋", "novel-cn-commercial-emotion"),
        ("年代, 种田", "novel-cn-history-society"),
        ("知乎短篇, 规则怪谈", "novel-cn-concept-short"),
        ("电竞, 直播文", "novel-cn-profession-live"),
    ],
)
def test_new_genre_capabilities_are_selected_from_creator_terms(
    genre: str, expected_skill: str
) -> None:
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={"language": "zh-CN", "platform": "番茄", "genre": genre},
    )

    plan = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile,
        role_key="writer",
        stage="writing",
    )

    assert expected_skill in {selection.skill.name for selection in plan.selections}
