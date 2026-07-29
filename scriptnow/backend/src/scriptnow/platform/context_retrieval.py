from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

RETRIEVAL_MANIFEST_SCHEMA_VERSION = 1


class RetrievalMode(StrEnum):
    CANONICAL = "canonical"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    NARRATIVE_GRAPH = "narrative_graph"
    TRANSLATION_MEMORY = "translation_memory"
    EXTERNAL = "external"


class RetrievalStopReason(StrEnum):
    COMPLETE = "complete"
    COVERAGE_MET = "coverage_met"
    POLICY_LIMIT = "policy_limit"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextRequest(FrozenContract):
    tenant_id: str = Field(min_length=1, max_length=36)
    project_id: str = Field(min_length=1, max_length=36)
    retrieval_project_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    domain: str = Field(min_length=1, max_length=40)
    stage: str = Field(min_length=1, max_length=120)
    operation: str = Field(min_length=1, max_length=120)
    unit_ref: str | None = Field(default=None, max_length=160)
    user_intent: str | None = Field(default=None, max_length=4000)
    required_dimensions: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    risk_level: str = Field(min_length=1, max_length=40)
    policy_ref: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_required_dimensions(self) -> ContextRequest:
        if len(self.required_dimensions) != len(set(self.required_dimensions)):
            raise ValueError("required dimensions must be unique")
        if len(self.retrieval_project_ids) != len(set(self.retrieval_project_ids)):
            raise ValueError("retrieval project ids must be unique")
        return self


class RetrievalPolicy(FrozenContract):
    allowed_sources: tuple[str, ...] = Field(min_length=1, max_length=50)
    retrieval_modes: tuple[RetrievalMode, ...] = Field(min_length=1, max_length=10)
    coverage_requirements: dict[str, float] = Field(default_factory=dict, max_length=50)
    token_limit: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_iterations: int = Field(gt=0)
    conflict_policy: str = Field(min_length=1, max_length=80)
    external_research_enabled: bool

    @model_validator(mode="after")
    def validate_policy_collections(self) -> RetrievalPolicy:
        if len(self.allowed_sources) != len(set(self.allowed_sources)):
            raise ValueError("allowed sources must be unique")
        if len(self.retrieval_modes) != len(set(self.retrieval_modes)):
            raise ValueError("retrieval modes must be unique")
        invalid_coverage = {
            key: value
            for key, value in self.coverage_requirements.items()
            if not 0 <= value <= 1
        }
        if invalid_coverage:
            raise ValueError("coverage requirements must be between 0 and 1")
        return self


class EvidenceRef(FrozenContract):
    ref_id: str = Field(min_length=1, max_length=160)
    source_type: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=240)
    source_version: str = Field(min_length=1, max_length=160)
    locator: dict[str, Any] = Field(default_factory=dict)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    score: float | None = None
    retrieval_modes: tuple[RetrievalMode, ...] = Field(default_factory=tuple, max_length=10)
    excerpt: str | None = None
    dimensions: tuple[str, ...] = Field(default_factory=tuple, max_length=50)
    token_count: int = Field(default=0, ge=0)
    fact_key: str | None = Field(default=None, max_length=240)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextPack(FrozenContract):
    task_contract: dict[str, Any]
    canonical_facts: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    latest_revisions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    domain_state: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = Field(default_factory=tuple)
    conflicts: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    omissions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    provenance: dict[str, Any] = Field(default_factory=dict)


class RetrievalQuery(FrozenContract):
    query: str = Field(min_length=1, max_length=4000)
    iteration: int = Field(ge=1)
    mode: RetrievalMode
    purpose: str = Field(min_length=1, max_length=500)
    dimensions: tuple[str, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_dimensions(self) -> RetrievalQuery:
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("query dimensions must be unique")
        return self


class RetrievalManifestPayload(FrozenContract):
    schema_version: int = Field(default=RETRIEVAL_MANIFEST_SCHEMA_VERSION, frozen=True)
    request: ContextRequest
    policy: RetrievalPolicy
    source_versions: dict[str, Any] = Field(default_factory=dict)
    queries: tuple[RetrievalQuery, ...] = Field(default_factory=tuple)
    hit_refs: tuple[EvidenceRef, ...] = Field(default_factory=tuple)
    graph_paths: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    excluded_refs: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    coverage: dict[str, float] = Field(default_factory=dict)
    conflicts: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    omissions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    stop_reason: RetrievalStopReason

    @model_validator(mode="after")
    def validate_manifest_scope_and_coverage(self) -> RetrievalManifestPayload:
        invalid_coverage = {
            key: value for key, value in self.coverage.items() if not 0 <= value <= 1
        }
        if invalid_coverage:
            raise ValueError("retrieval coverage must be between 0 and 1")
        unknown_dimensions = set(self.coverage) - set(self.request.required_dimensions)
        if unknown_dimensions:
            raise ValueError("retrieval coverage contains unrequested dimensions")
        return self
