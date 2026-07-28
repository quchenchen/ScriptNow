from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scriptnow.diagnostics.creative_flow_evidence import collect_persisted_evidence
from scriptnow.platform.creative_flow_audit import (
    FlowAuditReport,
    GoldenScenario,
    audit_flow,
    load_scenario,
)
from scriptnow.platform.models import (
    ProjectModel,
    ProjectRunModel,
    RuntimeConfigSnapshotModel,
)


class RealProviderReplayError(RuntimeError):
    pass


class ProviderProof(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_ref: str
    run_ref: str
    runtime_fingerprint: str
    provider_ref: str
    model_ref: str


class DomainReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    proof: ProviderProof
    audit: FlowAuditReport


class FourDomainReplayReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "real-provider-golden-replay/v1"
    passed: bool
    results: list[DomainReplayResult]


def _opaque_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


async def _provider_proof(
    session: AsyncSession,
    *,
    project: ProjectModel,
) -> ProviderProof:
    row = (
        await session.execute(
            select(RuntimeConfigSnapshotModel, ProjectRunModel)
            .join(
                ProjectRunModel,
                ProjectRunModel.id == RuntimeConfigSnapshotModel.run_id,
            )
            .where(ProjectRunModel.project_id == project.id)
            .order_by(RuntimeConfigSnapshotModel.created_at.desc())
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        raise RealProviderReplayError(
            f"project {_opaque_ref(project.id)} has no persisted runtime snapshot"
        )
    snapshot, run = row
    provider_key = str(snapshot.snapshot.get("provider_key") or "")
    model_key = str(snapshot.snapshot.get("model_key") or "")
    if not provider_key or not model_key:
        raise RealProviderReplayError(
            f"project {_opaque_ref(project.id)} runtime snapshot is incomplete"
        )
    if provider_key.casefold().startswith("mock") or model_key.casefold().startswith("mock"):
        raise RealProviderReplayError(
            f"project {_opaque_ref(project.id)} used a mock runtime"
        )
    return ProviderProof(
        project_ref=_opaque_ref(project.id),
        run_ref=_opaque_ref(run.id),
        runtime_fingerprint=snapshot.fingerprint,
        provider_ref=_opaque_ref(provider_key),
        model_ref=_opaque_ref(model_key),
    )


async def replay_persisted_four_domain_flows(
    session: AsyncSession,
    *,
    golden_root: Path,
    project_ids: dict[str, str],
) -> FourDomainReplayReport:
    scenario_files = {
        "novel": "novel-original.json",
        "script": "script-original.json",
        "translation": "faithful-translation.json",
        "recreation": "cross-cultural-recreation.json",
    }
    missing = sorted(set(scenario_files) - set(project_ids))
    unknown = sorted(set(project_ids) - set(scenario_files))
    if missing or unknown:
        raise RealProviderReplayError(
            f"four-domain project mapping is invalid: missing={missing}; unknown={unknown}"
        )

    results: list[DomainReplayResult] = []
    for domain, scenario_file in scenario_files.items():
        project = await session.get(ProjectModel, project_ids[domain])
        if project is None or project.deleted_at is not None:
            raise RealProviderReplayError(f"{domain} project does not exist or is deleted")
        scenario: GoldenScenario = load_scenario(golden_root / scenario_file)
        proof = await _provider_proof(session, project=project)
        observation = await collect_persisted_evidence(
            session,
            scenario=scenario,
            project_id=project.id,
        )
        results.append(
            DomainReplayResult(
                scenario_id=scenario.id,
                proof=proof,
                audit=audit_flow(scenario, observation),
            )
        )
    return FourDomainReplayReport(
        passed=all(item.audit.passed for item in results),
        results=results,
    )
