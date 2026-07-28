from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FlowErrorCategory(StrEnum):
    CONTRACT_VALIDATION = "contract_validation"
    PROVIDER = "provider"
    TIMEOUT = "timeout"
    PERSISTENCE = "persistence"
    PROJECTION = "projection"
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    RECOVERY = "recovery"
    DOMAIN_QUALITY = "domain_quality"
    UNKNOWN = "unknown"


class GoldenStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    required_artifacts: list[str] = Field(min_length=1)
    decision_required: bool = False


class GoldenScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["creative-flow-golden/v1"]
    id: str
    domain: Literal["novel", "script", "translation", "recreation"]
    workflow: str
    description: str
    stages: list[GoldenStage] = Field(min_length=1)

    @model_validator(mode="after")
    def stages_are_unique(self) -> GoldenScenario:
        stage_ids = [stage.id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("stage ids must be unique")
        return self


class ObservedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    revision: str
    readable: bool
    persisted: bool
    next_stage_consumable: bool


class ObservedDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    request_id: str
    resolved: bool
    resolution_count: int = Field(ge=0)


class ObservedStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["pending", "running", "waiting", "partial", "failed", "cancelled", "succeeded"]
    first_status_ms: int | None = Field(default=None, ge=0)
    first_content_ms: int | None = Field(default=None, ge=0)
    completed_ms: int | None = Field(default=None, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    artifacts: list[ObservedArtifact] = Field(default_factory=list)
    error_category: FlowErrorCategory | None = None


class FlowObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["creative-flow-observation/v1"]
    scenario_id: str
    operation_id: str
    status: Literal["pending", "running", "waiting", "partial", "failed", "cancelled", "succeeded"]
    stages: list[ObservedStage]
    decisions: list[ObservedDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_keys_are_unique(self) -> FlowObservation:
        stage_ids = [stage.id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("observed stage ids must be unique")
        request_ids = [decision.request_id for decision in self.decisions]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("decision request ids must be unique")
        return self


class AuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    code: str
    stage_id: str | None = None
    message: str


class FlowMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_status_ms: int | None
    first_content_ms: int | None
    total_ms: int | None
    input_tokens: int
    output_tokens: int


class FlowAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["creative-flow-audit/v1"] = "creative-flow-audit/v1"
    scenario_id: str
    operation_id: str
    passed: bool
    completion_invariant_satisfied: bool
    metrics: FlowMetrics
    findings: list[AuditFinding]


def load_scenario(path: Path) -> GoldenScenario:
    return GoldenScenario.model_validate_json(path.read_text(encoding="utf-8"))


def load_observation(path: Path) -> FlowObservation:
    return FlowObservation.model_validate_json(path.read_text(encoding="utf-8"))


def audit_flow(scenario: GoldenScenario, observation: FlowObservation) -> FlowAuditReport:
    findings: list[AuditFinding] = []
    if observation.scenario_id != scenario.id:
        findings.append(
            AuditFinding(
                severity="error",
                code="scenario_mismatch",
                message="观测记录与黄金场景不匹配。",
            )
        )

    observed_stages = {stage.id: stage for stage in observation.stages}
    decisions_by_stage: dict[str, list[ObservedDecision]] = {}
    for decision in observation.decisions:
        decisions_by_stage.setdefault(decision.stage_id, []).append(decision)

    for expected in scenario.stages:
        observed = observed_stages.get(expected.id)
        if observed is None:
            findings.append(
                AuditFinding(
                    severity="error",
                    code="missing_stage",
                    stage_id=expected.id,
                    message="缺少必需阶段的运行证据。",
                )
            )
            continue
        if observed.status != "succeeded":
            findings.append(
                AuditFinding(
                    severity="error",
                    code="stage_not_succeeded",
                    stage_id=expected.id,
                    message=f"阶段状态为 {observed.status}，未形成可消费完成态。",
                )
            )
        artifacts_by_kind: dict[str, list[ObservedArtifact]] = {}
        for artifact in observed.artifacts:
            artifacts_by_kind.setdefault(artifact.kind, []).append(artifact)
        for kind in expected.required_artifacts:
            valid = any(
                artifact.persisted and artifact.readable and artifact.next_stage_consumable
                for artifact in artifacts_by_kind.get(kind, [])
            )
            if not valid:
                findings.append(
                    AuditFinding(
                        severity="error",
                        code="missing_consumable_artifact",
                        stage_id=expected.id,
                        message=f"缺少已落盘、可读取且可供下一阶段消费的 {kind} 产物。",
                    )
                )
        if expected.decision_required:
            decisions = decisions_by_stage.get(expected.id, [])
            if not decisions or any(
                not item.resolved or item.resolution_count != 1 for item in decisions
            ):
                findings.append(
                    AuditFinding(
                        severity="error",
                        code="decision_not_resolved_exactly_once",
                        stage_id=expected.id,
                        message="阶段所需人工决定未被持久化并恰好解析一次。",
                    )
                )

    completion_invariant_satisfied = not any(
        finding.severity == "error" for finding in findings
    )
    if observation.status == "succeeded" and not completion_invariant_satisfied:
        findings.insert(
            0,
            AuditFinding(
                severity="error",
                code="false_success",
                message="运行标记为成功，但领域产物完成不变式未满足。",
            ),
        )
    elif observation.status != "succeeded" and completion_invariant_satisfied:
        findings.append(
            AuditFinding(
                severity="warning",
                code="unpublished_success",
                message="领域产物已满足完成不变式，但 operation 尚未发布成功状态。",
            )
        )

    stages = observation.stages
    first_status_values = [item.first_status_ms for item in stages if item.first_status_ms is not None]
    first_content_values = [
        item.first_content_ms for item in stages if item.first_content_ms is not None
    ]
    completed_values = [item.completed_ms for item in stages if item.completed_ms is not None]
    return FlowAuditReport(
        scenario_id=scenario.id,
        operation_id=observation.operation_id,
        passed=observation.status == "succeeded" and completion_invariant_satisfied,
        completion_invariant_satisfied=completion_invariant_satisfied,
        metrics=FlowMetrics(
            first_status_ms=min(first_status_values) if first_status_values else None,
            first_content_ms=min(first_content_values) if first_content_values else None,
            total_ms=max(completed_values) if completed_values else None,
            input_tokens=sum(item.input_tokens for item in stages),
            output_tokens=sum(item.output_tokens for item in stages),
        ),
        findings=findings,
    )
