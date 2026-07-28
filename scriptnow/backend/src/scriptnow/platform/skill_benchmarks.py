from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillBenchmarkError(RuntimeError):
    pass


class QualityAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    weight: float = Field(gt=0, le=100)


class QualityGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_candidate_score: float = Field(ge=0, le=100)
    minimum_lift: float = Field(ge=-100, le=100)
    maximum_regressed_anchors: int = Field(ge=0, le=100)
    maximum_cost_multiplier: float = Field(gt=0, le=100)
    maximum_blocking_failures: int = Field(ge=0, le=100)


class SkillBenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=160)
    language: str = Field(min_length=2, max_length=16)
    platform: str = Field(min_length=1, max_length=80)
    genres: list[str] = Field(min_length=1, max_length=20)
    role: str = Field(pattern=r"^(director|architect|writer|reviewer)$")
    stage: str = Field(min_length=1, max_length=80)
    brief: str = Field(min_length=20, max_length=5000)
    anchor_keys: list[str] = Field(min_length=1, max_length=30)


class SkillBenchmarkSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^[a-z0-9-]+$")
    anchors: list[QualityAnchor] = Field(min_length=1, max_length=50)
    cases: list[SkillBenchmarkCase] = Field(min_length=1, max_length=500)
    gates: QualityGate

    @model_validator(mode="after")
    def validate_references(self) -> SkillBenchmarkSuite:
        anchor_keys = [anchor.key for anchor in self.anchors]
        if len(anchor_keys) != len(set(anchor_keys)):
            raise ValueError("benchmark anchor keys must be unique")
        case_keys = [case.key for case in self.cases]
        if len(case_keys) != len(set(case_keys)):
            raise ValueError("benchmark case keys must be unique")
        unknown = sorted(
            {
                anchor_key
                for case in self.cases
                for anchor_key in case.anchor_keys
                if anchor_key not in set(anchor_keys)
            }
        )
        if unknown:
            raise ValueError(f"benchmark cases reference unknown anchors: {', '.join(unknown)}")
        return self

    def anchor(self, key: str) -> QualityAnchor:
        try:
            return next(anchor for anchor in self.anchors if anchor.key == key)
        except StopIteration as error:
            raise SkillBenchmarkError(f"unknown quality anchor: {key}") from error

    def case(self, key: str) -> SkillBenchmarkCase:
        try:
            return next(case for case in self.cases if case.key == key)
        except StopIteration as error:
            raise SkillBenchmarkError(f"unknown benchmark case: {key}") from error


class SkillTrialResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_key: str = Field(pattern=r"^[a-z0-9-]+$")
    variant: Literal["baseline", "candidate"]
    anchor_scores: dict[str, float] = Field(min_length=1, max_length=50)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    blocking_failures: int = Field(default=0, ge=0)
    evaluator: str = Field(min_length=1, max_length=160)
    evidence: list[str] = Field(default_factory=list, max_length=100)


class AnchorComparison(BaseModel):
    key: str
    baseline: float
    candidate: float
    lift: float


class SkillBenchmarkReport(BaseModel):
    suite_version: str
    candidate_skill_digest: str
    case_count: int
    baseline_score: float
    candidate_score: float
    lift: float
    cost_multiplier: float
    blocking_failures: int
    regressed_anchors: list[str]
    anchor_comparisons: list[AnchorComparison]
    passed: bool
    failed_gates: list[str]


class SkillAdmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    skill_name: str
    candidate_skill_digest: str
    status: Literal["admitted", "quarantined"]
    quality_status: Literal["measured", "rejected"]
    benchmark_suite: str
    benchmark_report: str


def load_benchmark_suite(path: str | Path) -> SkillBenchmarkSuite:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
        return SkillBenchmarkSuite.model_validate(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SkillBenchmarkError(f"invalid skill benchmark suite: {source}") from error


def evaluate_skill_trials(
    *,
    suite: SkillBenchmarkSuite,
    candidate_skill_digest: str,
    trials: list[SkillTrialResult],
) -> SkillBenchmarkReport:
    paired: dict[str, dict[str, SkillTrialResult]] = defaultdict(dict)
    for trial in trials:
        case = suite.case(trial.case_key)
        unknown = sorted(set(trial.anchor_scores) - set(case.anchor_keys))
        missing = sorted(set(case.anchor_keys) - set(trial.anchor_scores))
        if unknown or missing:
            details = []
            if unknown:
                details.append(f"unknown={','.join(unknown)}")
            if missing:
                details.append(f"missing={','.join(missing)}")
            raise SkillBenchmarkError(
                f"trial anchors do not match case {trial.case_key}: {'; '.join(details)}"
            )
        for key, score in trial.anchor_scores.items():
            if not 0 <= score <= 100:
                raise SkillBenchmarkError(f"anchor score outside 0..100: {key}={score}")
        if trial.variant in paired[trial.case_key]:
            raise SkillBenchmarkError(
                f"duplicate {trial.variant} trial for case: {trial.case_key}"
            )
        paired[trial.case_key][trial.variant] = trial

    expected_cases = {case.key for case in suite.cases}
    if set(paired) != expected_cases:
        missing_cases = sorted(expected_cases - set(paired))
        extra_cases = sorted(set(paired) - expected_cases)
        raise SkillBenchmarkError(
            f"trial coverage does not match suite: missing={missing_cases}; extra={extra_cases}"
        )
    unpaired = sorted(
        case_key
        for case_key, variants in paired.items()
        if set(variants) != {"baseline", "candidate"}
    )
    if unpaired:
        raise SkillBenchmarkError(f"benchmark cases require paired trials: {', '.join(unpaired)}")

    weighted_baseline = 0.0
    weighted_candidate = 0.0
    total_weight = 0.0
    anchor_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"baseline": 0.0, "candidate": 0.0, "count": 0.0}
    )
    baseline_tokens = 0
    candidate_tokens = 0
    blocking_failures = 0

    for case_key, variants in paired.items():
        case = suite.case(case_key)
        baseline = variants["baseline"]
        candidate = variants["candidate"]
        baseline_tokens += baseline.input_tokens + baseline.output_tokens
        candidate_tokens += candidate.input_tokens + candidate.output_tokens
        blocking_failures += candidate.blocking_failures
        for anchor_key in case.anchor_keys:
            anchor = suite.anchor(anchor_key)
            weight = anchor.weight
            weighted_baseline += baseline.anchor_scores[anchor_key] * weight
            weighted_candidate += candidate.anchor_scores[anchor_key] * weight
            total_weight += weight
            anchor_totals[anchor_key]["baseline"] += baseline.anchor_scores[anchor_key]
            anchor_totals[anchor_key]["candidate"] += candidate.anchor_scores[anchor_key]
            anchor_totals[anchor_key]["count"] += 1

    baseline_score = weighted_baseline / total_weight
    candidate_score = weighted_candidate / total_weight
    comparisons = [
        AnchorComparison(
            key=key,
            baseline=values["baseline"] / values["count"],
            candidate=values["candidate"] / values["count"],
            lift=(values["candidate"] - values["baseline"]) / values["count"],
        )
        for key, values in sorted(anchor_totals.items())
    ]
    regressed = [comparison.key for comparison in comparisons if comparison.lift < 0]
    cost_multiplier = candidate_tokens / baseline_tokens if baseline_tokens else 1.0
    failed_gates: list[str] = []
    if candidate_score < suite.gates.minimum_candidate_score:
        failed_gates.append("minimum_candidate_score")
    if candidate_score - baseline_score < suite.gates.minimum_lift:
        failed_gates.append("minimum_lift")
    if len(regressed) > suite.gates.maximum_regressed_anchors:
        failed_gates.append("maximum_regressed_anchors")
    if cost_multiplier > suite.gates.maximum_cost_multiplier:
        failed_gates.append("maximum_cost_multiplier")
    if blocking_failures > suite.gates.maximum_blocking_failures:
        failed_gates.append("maximum_blocking_failures")

    return SkillBenchmarkReport(
        suite_version=suite.version,
        candidate_skill_digest=candidate_skill_digest,
        case_count=len(paired),
        baseline_score=round(baseline_score, 4),
        candidate_score=round(candidate_score, 4),
        lift=round(candidate_score - baseline_score, 4),
        cost_multiplier=round(cost_multiplier, 4),
        blocking_failures=blocking_failures,
        regressed_anchors=regressed,
        anchor_comparisons=comparisons,
        passed=not failed_gates,
        failed_gates=failed_gates,
    )


def record_skill_admission(
    *,
    registry_path: str | Path,
    domain: str,
    skill_name: str,
    report: SkillBenchmarkReport,
    report_path: str,
) -> SkillAdmissionResult:
    source = Path(registry_path)
    try:
        registry = json.loads(source.read_text(encoding="utf-8"))
        entry = registry["domains"][domain][skill_name]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SkillBenchmarkError(
            f"skill is not registered for admission: {domain}/{skill_name}"
        ) from error
    if not isinstance(entry, dict):
        raise SkillBenchmarkError(f"invalid admission entry: {domain}/{skill_name}")

    status = "admitted" if report.passed else "quarantined"
    quality_status = "measured" if report.passed else "rejected"
    entry.update(
        {
            "status": status,
            "quality_status": quality_status,
            "benchmark_suite": report.suite_version,
            "benchmark_report": report_path,
            "candidate_digest": report.candidate_skill_digest,
        }
    )
    rendered = f"{json.dumps(registry, ensure_ascii=False, indent=2)}\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=source.parent,
            prefix=f".{source.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, source)
    except OSError as error:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise SkillBenchmarkError(f"could not persist skill admission: {source}") from error

    return SkillAdmissionResult(
        domain=domain,
        skill_name=skill_name,
        candidate_skill_digest=report.candidate_skill_digest,
        status=status,
        quality_status=quality_status,
        benchmark_suite=report.suite_version,
        benchmark_report=report_path,
    )
