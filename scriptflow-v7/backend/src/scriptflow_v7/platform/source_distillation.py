from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    DistillationDecision,
    DistillationStatus,
    ProjectMedium,
    ProjectModel,
    RagChunkModel,
    SourceDistillationModel,
    SourceEvidenceModel,
    SourceProfileModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)

DISTILLATION_PASSES = (
    "inventory",
    "atomic_evidence",
    "cross_unit_synthesis",
    "conflict_gap_check",
    "candidate_profile",
    "human_decision",
)
EVIDENCE_DIMENSIONS = frozenset(
    {
        "plot_causality",
        "character_state",
        "relationship_state",
        "world_rule",
        "voice_feature",
        "setup_payoff",
        "quality_risk",
    }
)


class SourceDistillationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    evidence_key: str
    source_file_id: str
    chunk_id: str
    source_unit: str
    ordinal: int
    dimension: str
    claim: str
    confidence: int
    inference: bool = False
    related_evidence_ids: tuple[str, ...] = ()
    contradiction_group: str | None = None


class SourceDistillationService:
    """Persists a resumable, evidence-first source analysis workflow."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def start(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_file_ids: list[str],
        idempotency_key: str,
    ) -> SourceDistillationModel:
        unique_sources = list(dict.fromkeys(source_file_ids))
        if not unique_sources:
            raise SourceDistillationError("at least one source file is required")
        if not idempotency_key.strip() or len(idempotency_key) > 120:
            raise SourceDistillationError("invalid distillation idempotency key")
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(SourceDistillationModel).where(
                        SourceDistillationModel.tenant_id == tenant_id,
                        SourceDistillationModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                if existing.project_id != project_id or existing.source_file_ids != unique_sources:
                    raise SourceDistillationError(
                        "idempotency key has different distillation scope"
                    )
                return existing
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != tenant_id
                or project.medium != ProjectMedium.NOVEL
            ):
                raise SourceDistillationError("novel project does not exist in tenant")
            sources = list(
                await session.scalars(
                    select(WorkspaceFileModel).where(WorkspaceFileModel.id.in_(unique_sources))
                )
            )
            if len(sources) != len(unique_sources) or any(
                source.tenant_id != tenant_id
                or source.project_id != project_id
                or source.status != WorkspaceFileStatus.READY
                for source in sources
            ):
                raise SourceDistillationError("source is outside ready tenant workspace")
            indexed = set(
                await session.scalars(
                    select(RagChunkModel.source_file_id)
                    .where(RagChunkModel.source_file_id.in_(unique_sources))
                    .distinct()
                )
            )
            if indexed != set(unique_sources):
                raise SourceDistillationError(
                    "all source files must be indexed before distillation"
                )
            total_chunks = int(
                await session.scalar(
                    select(func.count(RagChunkModel.id)).where(
                        RagChunkModel.source_file_id.in_(unique_sources)
                    )
                )
                or 0
            )
            run = SourceDistillationModel(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
                source_file_ids=unique_sources,
                checkpoint={"processed_chunk_ids": [], "pass_attempts": {}},
                coverage={"processed_chunks": 0, "total_chunks": total_chunks, "dimensions": {}},
            )
            session.add(run)
            await session.flush()
            return run

    async def record_evidence(
        self, *, tenant_id: str, distillation_id: str, item: EvidenceInput
    ) -> SourceEvidenceModel:
        if item.dimension not in EVIDENCE_DIMENSIONS:
            raise SourceDistillationError("unsupported evidence dimension")
        if not item.evidence_key.strip() or not item.claim.strip() or not item.source_unit.strip():
            raise SourceDistillationError("evidence key, source unit and claim are required")
        if not 0 <= item.confidence <= 100:
            raise SourceDistillationError("evidence confidence must be between 0 and 100")
        async with self.database.session() as session:
            run = await self._run(session, tenant_id, distillation_id)
            if run.status != DistillationStatus.RUNNING:
                raise SourceDistillationError("distillation is not accepting evidence")
            existing = (
                await session.scalars(
                    select(SourceEvidenceModel).where(
                        SourceEvidenceModel.distillation_id == run.id,
                        SourceEvidenceModel.evidence_key == item.evidence_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return existing
            chunk = await session.get(RagChunkModel, item.chunk_id)
            if (
                chunk is None
                or chunk.tenant_id != tenant_id
                or chunk.project_id != run.project_id
                or chunk.source_file_id != item.source_file_id
                or item.source_file_id not in run.source_file_ids
                or chunk.ordinal != item.ordinal
            ):
                raise SourceDistillationError("evidence citation is outside distillation scope")
            related = set(
                await session.scalars(
                    select(SourceEvidenceModel.id).where(
                        SourceEvidenceModel.id.in_(item.related_evidence_ids),
                        SourceEvidenceModel.distillation_id == run.id,
                    )
                )
            )
            if related != set(item.related_evidence_ids):
                raise SourceDistillationError("related evidence is outside distillation run")
            evidence = SourceEvidenceModel(
                tenant_id=tenant_id,
                project_id=run.project_id,
                distillation_id=run.id,
                evidence_key=item.evidence_key,
                source_file_id=item.source_file_id,
                chunk_id=item.chunk_id,
                source_unit=item.source_unit,
                ordinal=item.ordinal,
                dimension=item.dimension,
                claim=item.claim.strip(),
                confidence=item.confidence,
                inference=item.inference,
                related_evidence_ids=list(item.related_evidence_ids),
                contradiction_group=item.contradiction_group,
                extraction_pass=run.pass_key,
            )
            session.add(evidence)
            await session.flush()
            return evidence

    async def set_related_evidence(
        self,
        *,
        tenant_id: str,
        distillation_id: str,
        evidence_id: str,
        related_evidence_ids: tuple[str, ...],
    ) -> SourceEvidenceModel:
        """Attach relations after a complete analyzer batch has been materialized.

        Analyzer output may contain forward or mutual references within one batch. Those
        references cannot be represented until every evidence row has an ID, so the runner
        creates the rows first and links them in this second phase.
        """
        async with self.database.session() as session:
            run = await self._run(session, tenant_id, distillation_id)
            if run.status != DistillationStatus.RUNNING:
                raise SourceDistillationError("distillation is not accepting evidence")
            evidence = await session.get(SourceEvidenceModel, evidence_id)
            if evidence is None or evidence.distillation_id != run.id:
                raise SourceDistillationError("evidence is outside distillation run")
            related = set(
                await session.scalars(
                    select(SourceEvidenceModel.id).where(
                        SourceEvidenceModel.id.in_(related_evidence_ids),
                        SourceEvidenceModel.distillation_id == run.id,
                    )
                )
            )
            if related != set(related_evidence_ids):
                raise SourceDistillationError("related evidence is outside distillation run")
            evidence.related_evidence_ids = list(dict.fromkeys(related_evidence_ids))
            await session.flush()
            return evidence

    async def checkpoint(
        self,
        *,
        tenant_id: str,
        distillation_id: str,
        next_pass: str,
        processed_chunk_ids: list[str],
        coverage: dict[str, object],
        checkpoint_extra: dict[str, object] | None = None,
    ) -> SourceDistillationModel:
        if next_pass not in DISTILLATION_PASSES:
            raise SourceDistillationError("unsupported distillation pass")
        async with self.database.session() as session:
            run = await self._run(session, tenant_id, distillation_id)
            if run.status != DistillationStatus.RUNNING:
                raise SourceDistillationError("distillation is not running")
            current = DISTILLATION_PASSES.index(run.pass_key)
            following = DISTILLATION_PASSES.index(next_pass)
            if following < current or following > current + 1:
                raise SourceDistillationError("distillation pass transition is invalid")
            valid = set(
                await session.scalars(
                    select(RagChunkModel.id).where(
                        RagChunkModel.project_id == run.project_id,
                        RagChunkModel.source_file_id.in_(run.source_file_ids),
                    )
                )
            )
            processed = list(dict.fromkeys(processed_chunk_ids))
            if not set(processed) <= valid:
                raise SourceDistillationError("checkpoint references unknown source chunks")
            attempts = dict(dict(run.checkpoint).get("pass_attempts") or {})
            attempts[run.pass_key] = int(attempts.get(run.pass_key, 0)) + 1
            run.pass_key = next_pass
            existing_extra = {
                key: value
                for key, value in dict(run.checkpoint).items()
                if key not in {"processed_chunk_ids", "pass_attempts"}
            }
            extra = {
                key: value
                for key, value in dict(checkpoint_extra or {}).items()
                if key not in {"processed_chunk_ids", "pass_attempts"}
            }
            run.checkpoint = {
                "processed_chunk_ids": processed,
                "pass_attempts": attempts,
                **existing_extra,
                **extra,
            }
            run.coverage = {
                **coverage,
                "processed_chunks": len(processed),
                "total_chunks": len(valid),
            }
            await session.flush()
            return run

    async def create_candidate(
        self,
        *,
        tenant_id: str,
        distillation_id: str,
        profile: dict[str, object],
        evidence_ids: list[str],
        conflicts: list[dict[str, object]],
        exclusions: list[str],
        ready_with_gaps: bool,
    ) -> SourceProfileModel:
        if not profile or not evidence_ids:
            raise SourceDistillationError("candidate profile requires cited evidence")
        async with self.database.session() as session:
            run = await self._run(session, tenant_id, distillation_id)
            if run.status != DistillationStatus.RUNNING:
                raise SourceDistillationError("distillation cannot create another candidate")
            if run.pass_key not in {"candidate_profile", "human_decision"}:
                raise SourceDistillationError("distillation has not reached candidate synthesis")
            valid = set(
                await session.scalars(
                    select(SourceEvidenceModel.id).where(
                        SourceEvidenceModel.distillation_id == run.id,
                        SourceEvidenceModel.id.in_(evidence_ids),
                    )
                )
            )
            if valid != set(evidence_ids):
                raise SourceDistillationError("candidate references unknown evidence")
            version = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(SourceProfileModel.version), 0)).where(
                            SourceProfileModel.project_id == run.project_id
                        )
                    )
                    or 0
                )
                + 1
            )
            candidate = SourceProfileModel(
                tenant_id=tenant_id,
                project_id=run.project_id,
                distillation_id=run.id,
                version=version,
                profile=profile,
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                conflicts=conflicts,
                exclusions=list(dict.fromkeys(exclusions)),
            )
            session.add(candidate)
            run.pass_key = "human_decision"
            run.status = (
                DistillationStatus.READY_WITH_GAPS if ready_with_gaps else DistillationStatus.READY
            )
            await session.flush()
            return candidate

    async def decide(
        self,
        *,
        tenant_id: str,
        project_id: str,
        profile_id: str,
        approve: bool,
        feedback: str | None = None,
    ) -> SourceProfileModel:
        async with self.database.session() as session:
            profile = await session.get(SourceProfileModel, profile_id)
            if (
                profile is None
                or profile.tenant_id != tenant_id
                or profile.project_id != project_id
            ):
                raise SourceDistillationError("source profile does not exist in tenant project")
            if profile.decision != DistillationDecision.CANDIDATE:
                raise SourceDistillationError("source profile decision is already final")
            profile.decision = (
                DistillationDecision.APPROVED if approve else DistillationDecision.REJECTED
            )
            profile.decision_feedback = feedback.strip() if feedback else None
            profile.decided_at = datetime.now(UTC)
            await session.flush()
            return profile

    async def approved_profile(
        self, *, tenant_id: str, project_id: str
    ) -> SourceProfileModel | None:
        async with self.database.session() as session:
            query = (
                select(SourceProfileModel)
                .where(
                    SourceProfileModel.tenant_id == tenant_id,
                    SourceProfileModel.project_id == project_id,
                    SourceProfileModel.decision == DistillationDecision.APPROVED,
                )
                .order_by(SourceProfileModel.version.desc())
            )
            return (await session.scalars(query)).first()

    @staticmethod
    async def _run(session, tenant_id: str, distillation_id: str) -> SourceDistillationModel:
        run = await session.get(SourceDistillationModel, distillation_id)
        if run is None or run.tenant_id != tenant_id:
            raise SourceDistillationError("distillation does not exist in tenant")
        return run
