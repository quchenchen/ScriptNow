import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from scriptnow.platform.agent_runtime import AgentRuntimeResult
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    RagChunkModel,
    SourceEvidenceModel,
    SourceProfileModel,
    TenantModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)
from scriptnow.platform.source_distillation import (
    EvidenceInput,
    SourceDistillationError,
    SourceDistillationService,
)
from scriptnow.platform.source_distillation_runner import (
    AgentRuntimeDistillationAnalyzer,
    AnalyzerOutputError,
    EvidenceDraft,
    SourceDistillationRunner,
)


@pytest.fixture
async def distillation_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Moonbound", medium=ProjectMedium.NOVEL)
        session.add(project)
        await session.flush()
        source = WorkspaceFileModel(
            tenant_id=tenant.id,
            project_id=project.id,
            original_name="source.docx",
            storage_name="source.docx",
            media_type="application/docx",
            byte_size=100,
            sha256="0" * 64,
            status=WorkspaceFileStatus.READY,
        )
        session.add(source)
        await session.flush()
        chunks = [
            RagChunkModel(
                tenant_id=tenant.id,
                project_id=project.id,
                source_file_id=source.id,
                ordinal=index,
                content=text,
                content_hash=str(index) * 64,
            )
            for index, text in enumerate(("Sera is rejected.", "The bond protects her."))
        ]
        session.add_all(chunks)
        await session.flush()
    yield database, tenant, other, project, source, chunks
    await database.dispose()


@pytest.mark.asyncio
async def test_distillation_is_resumable_evidence_first_and_human_approved(
    distillation_data,
) -> None:
    database, tenant, _, project, source, chunks = distillation_data
    service = SourceDistillationService(database)
    run = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="moonbound-v1",
    )
    repeated = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="moonbound-v1",
    )
    assert repeated.id == run.id
    assert run.coverage["total_chunks"] == 2

    run = await service.checkpoint(
        tenant_id=tenant.id,
        distillation_id=run.id,
        next_pass="atomic_evidence",
        processed_chunk_ids=[],
        coverage={"dimensions": {}},
    )
    evidence = await service.record_evidence(
        tenant_id=tenant.id,
        distillation_id=run.id,
        item=EvidenceInput(
            evidence_key="rejection-protects",
            source_file_id=source.id,
            chunk_id=chunks[1].id,
            source_unit="chapter-1",
            ordinal=1,
            dimension="relationship_state",
            claim="The rejection functions as protection rather than abandonment.",
            confidence=88,
        ),
    )
    repeated_evidence = await service.record_evidence(
        tenant_id=tenant.id,
        distillation_id=run.id,
        item=EvidenceInput(
            evidence_key="rejection-protects",
            source_file_id=source.id,
            chunk_id=chunks[1].id,
            source_unit="chapter-1",
            ordinal=1,
            dimension="relationship_state",
            claim="Ignored duplicate",
            confidence=1,
        ),
    )
    assert repeated_evidence.id == evidence.id

    for next_pass in ("cross_unit_synthesis", "conflict_gap_check", "candidate_profile"):
        run = await service.checkpoint(
            tenant_id=tenant.id,
            distillation_id=run.id,
            next_pass=next_pass,
            processed_chunk_ids=[chunk.id for chunk in chunks],
            coverage={"dimensions": {"relationship_state": 1}},
        )
    candidate = await service.create_candidate(
        tenant_id=tenant.id,
        distillation_id=run.id,
        profile={"relationship_engine": "rejection-as-protection must remain ambiguous"},
        evidence_ids=[evidence.id],
        conflicts=[],
        exclusions=["author imitation"],
        ready_with_gaps=True,
    )
    assert candidate.decision == "candidate"
    assert candidate.evidence_ids == [evidence.id]
    assert (
        await service.decide(
            tenant_id=tenant.id,
            project_id=project.id,
            profile_id=candidate.id,
            approve=True,
            feedback="Keep the anti-trope premise.",
        )
    ).decision == "approved"

    async with database.session() as session:
        stored = await session.scalar(
            select(SourceProfileModel).where(SourceProfileModel.id == candidate.id)
        )
        assert stored is not None and stored.decision_feedback


@pytest.mark.asyncio
async def test_distillation_rejects_cross_tenant_access(distillation_data) -> None:
    database, tenant, other, project, source, _ = distillation_data
    service = SourceDistillationService(database)
    run = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="tenant-bound",
    )

    with pytest.raises(SourceDistillationError, match="does not exist in tenant"):
        await service.checkpoint(
            tenant_id=other.id,
            distillation_id=run.id,
            next_pass="atomic_evidence",
            processed_chunk_ids=[],
            coverage={},
        )


class _DeterministicAnalyzer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(pass_key)
        if pass_key == "atomic_evidence":
            return {
                "evidence": [
                    {
                        "evidence_key": f"atomic-{chunk['ordinal']}",
                        "chunk_id": chunk["chunk_id"],
                        "source_unit": "chapter-1",
                        "dimension": "relationship_state",
                        "claim": f"Observed source claim {chunk['ordinal']}",
                        "confidence": 90,
                    }
                    for chunk in payload["chunks"]
                ]
            }
        if pass_key == "cross_unit_synthesis":
            first = payload["evidence"][0]
            return {
                "evidence": [
                    {
                        "evidence_key": "synthesis-rejection-protection",
                        "chunk_id": first["chunk_id"],
                        "source_unit": "whole-work",
                        "dimension": "relationship_state",
                        "claim": "Rejection repeatedly functions as protection.",
                        "confidence": 84,
                        "inference": True,
                        "related_evidence_keys": [first["evidence_key"]],
                    }
                ]
            }
        if pass_key == "conflict_gap_check":
            return {
                "conflicts": [],
                "gaps": ["voice evidence needs another pass"],
                "dimension_coverage": {"relationship_state": 1},
            }
        if pass_key == "candidate_profile":
            return {
                "profile": {
                    "relationship_engine": "rejection-as-protection",
                    "quality_constraints": ["preserve ambiguity"],
                },
                "evidence_keys": ["synthesis-rejection-protection"],
                "exclusions": ["author imitation"],
                "ready_with_gaps": False,
            }
        raise AssertionError(pass_key)


class _ForwardReferenceAnalyzer(_DeterministicAnalyzer):
    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        if pass_key != "atomic_evidence":
            return await super().analyze(pass_key=pass_key, payload=payload)
        chunks = payload["chunks"]
        return {
            "evidence": [
                {
                    "evidence_key": "first-in-output",
                    "chunk_id": chunks[0]["chunk_id"],
                    "source_unit": "chapter-1",
                    "dimension": "relationship_state",
                    "claim": "The first claim depends on a later item in the same batch.",
                    "confidence": 90,
                    "related_evidence_keys": ["later-in-output"],
                },
                {
                    "evidence_key": "later-in-output",
                    "chunk_id": chunks[-1]["chunk_id"],
                    "source_unit": "chapter-1",
                    "dimension": "character_state",
                    "claim": "The later item supplies the related character state.",
                    "confidence": 88,
                },
            ]
        }


@pytest.mark.asyncio
async def test_runner_resolves_forward_references_within_analyzer_batch(
    distillation_data,
) -> None:
    database, tenant, _, project, source, _ = distillation_data
    service = SourceDistillationService(database)
    run = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="forward-reference-batch",
    )

    result = await SourceDistillationRunner(
        database, _ForwardReferenceAnalyzer(), chunk_batch_size=2, evidence_batch_size=5
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    assert result.processed_chunks == 2
    async with database.session() as session:
        evidence = list(
            (
                await session.scalars(
                    select(SourceEvidenceModel).where(
                        SourceEvidenceModel.distillation_id == run.id,
                        SourceEvidenceModel.extraction_pass == "atomic_evidence",
                    )
                )
            ).all()
        )
    by_key = {item.evidence_key: item for item in evidence}
    assert by_key["first-in-output"].related_evidence_ids == [by_key["later-in-output"].id]


class _RepairingChunkCitationAnalyzer(_DeterministicAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.atomic_attempts = 0
        self.repair_feedback: str | None = None

    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        if pass_key != "atomic_evidence":
            return await super().analyze(pass_key=pass_key, payload=payload)
        self.atomic_attempts += 1
        self.repair_feedback = payload.get("validation_feedback")
        chunk_id = (
            "invented-chunk-id"
            if self.atomic_attempts == 1
            else payload["allowed_chunk_ids"][0]
        )
        return {
            "evidence": [
                {
                    "evidence_key": "repairable-citation",
                    "chunk_id": chunk_id,
                    "source_unit": "chapter-1",
                    "dimension": "character_state",
                    "claim": "A grounded character-state observation.",
                    "confidence": 86,
                }
            ]
        }


@pytest.mark.asyncio
async def test_runner_retries_invalid_chunk_citation_with_contract_feedback(
    distillation_data,
) -> None:
    database, tenant, _, project, source, _ = distillation_data
    run = await SourceDistillationService(database).start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="repair-invalid-citation",
    )
    analyzer = _RepairingChunkCitationAnalyzer()

    result = await SourceDistillationRunner(
        database, analyzer, chunk_batch_size=2, evidence_batch_size=5
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    assert result.processed_chunks == 2
    assert analyzer.atomic_attempts == 2
    assert analyzer.repair_feedback == "unknown cited chunk: invented-chunk-id"


class _RepairingNonObjectAnalyzer(_DeterministicAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.atomic_attempts = 0

    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        if pass_key != "atomic_evidence":
            return await super().analyze(pass_key=pass_key, payload=payload)
        self.atomic_attempts += 1
        if self.atomic_attempts == 1:
            raise AnalyzerOutputError("atomic_evidence did not return a JSON object")
        return {
            "evidence": [
                {
                    "evidence_key": "repaired-json-object",
                    "chunk_id": payload["allowed_chunk_ids"][0],
                    "source_unit": "chapter-1",
                    "dimension": "character_state",
                    "claim": "The repaired response is contract-valid.",
                    "confidence": 82,
                }
            ]
        }


@pytest.mark.asyncio
async def test_runner_retries_non_object_analyzer_response(distillation_data) -> None:
    database, tenant, _, project, source, _ = distillation_data
    run = await SourceDistillationService(database).start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="repair-non-object",
    )
    analyzer = _RepairingNonObjectAnalyzer()

    result = await SourceDistillationRunner(
        database, analyzer, chunk_batch_size=2, evidence_batch_size=5
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    assert result.processed_chunks == 2
    assert analyzer.atomic_attempts == 2


class _VerboseSourceUnitAnalyzer(_DeterministicAnalyzer):
    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        if pass_key != "atomic_evidence":
            return await super().analyze(pass_key=pass_key, payload=payload)
        return {
            "evidence": [
                {
                    "evidence_key": "verbose-source-unit",
                    "chunk_id": payload["allowed_chunk_ids"][0],
                    "source_unit": "misplaced source prose " * 30,
                    "dimension": "character_state",
                    "claim": "The claim remains intact while its locator is normalized.",
                    "confidence": 80,
                }
            ]
        }


@pytest.mark.asyncio
async def test_runner_normalizes_prose_misplaced_in_source_unit(distillation_data) -> None:
    database, tenant, _, project, source, _ = distillation_data
    run = await SourceDistillationService(database).start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="normalize-source-unit",
    )

    await SourceDistillationRunner(
        database, _VerboseSourceUnitAnalyzer(), chunk_batch_size=2, evidence_batch_size=5
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    async with database.session() as session:
        item = (
            await session.scalars(
                select(SourceEvidenceModel).where(
                    SourceEvidenceModel.distillation_id == run.id,
                    SourceEvidenceModel.evidence_key == "verbose-source-unit",
                )
            )
        ).one()
    assert item.source_unit == "chunk-0"
    assert item.claim == "The claim remains intact while its locator is normalized."


@pytest.mark.asyncio
async def test_runner_executes_multi_pass_loop_and_stops_for_human_decision(
    distillation_data,
) -> None:
    database, tenant, _, project, source, _ = distillation_data
    service = SourceDistillationService(database)
    run = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="autonomous-loop",
    )
    analyzer = _DeterministicAnalyzer()
    result = await SourceDistillationRunner(
        database, analyzer, chunk_batch_size=1, evidence_batch_size=5
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    assert result.status == "ready_with_gaps"
    assert result.processed_chunks == 2
    assert result.evidence_count == 3
    assert analyzer.calls == [
        "atomic_evidence",
        "atomic_evidence",
        "cross_unit_synthesis",
        "conflict_gap_check",
        "candidate_profile",
    ]
    async with database.session() as session:
        profile = await session.get(SourceProfileModel, result.profile_id)
        assert profile is not None
        assert profile.decision == "candidate"
        assert profile.profile["relationship_engine"] == "rejection-as-protection"
        assert profile.exclusions == ["author imitation"]


class _RuntimeProbe:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def generate(self, **kwargs) -> AgentRuntimeResult:
        self.kwargs = kwargs
        return AgentRuntimeResult(
            text='{"evidence": []}',
            runtime="agentscope",
            model_key="model-v1",
            input_tokens=11,
            output_tokens=7,
            input_price_per_million=Decimal("1"),
            output_price_per_million=Decimal("2"),
        )


@pytest.mark.asyncio
async def test_runtime_analyzer_mounts_only_distiller_and_reports_usage() -> None:
    runtime = _RuntimeProbe()
    usage: list[tuple[str, int, int]] = []

    async def sink(pass_key: str, call_index: int, result: AgentRuntimeResult) -> None:
        usage.append((pass_key, call_index, result.input_tokens + result.output_tokens))

    analyzer = AgentRuntimeDistillationAnalyzer(
        runtime,  # type: ignore[arg-type]
        tenant_id="tenant-1",
        run_id="run-1",
        usage_sink=sink,
        selected_model_id="flash-extract",
    )
    assert await analyzer.analyze(pass_key="atomic_evidence", payload={"chunks": []}) == {
        "evidence": []
    }
    assert runtime.kwargs["stage_override"] == "source-analysis"
    assert runtime.kwargs["explicit_skill_keys"] == ("novel-source-distiller",)
    assert runtime.kwargs["selected_model_id"] == "flash-extract"
    assert usage == [("atomic_evidence", 1, 18)]
    await analyzer.analyze(pass_key="candidate_profile", payload={})
    assert runtime.kwargs["selected_model_id"] is None


class _SlowAtomicAnalyzer(_DeterministicAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.in_flight: dict[str, int] = {}
        self.max_in_flight: dict[str, int] = {}
        self.lock = asyncio.Lock()

    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        if pass_key not in {"atomic_evidence", "cross_unit_synthesis"}:
            return await super().analyze(pass_key=pass_key, payload=payload)
        async with self.lock:
            in_flight = self.in_flight.get(pass_key, 0) + 1
            self.in_flight[pass_key] = in_flight
            self.max_in_flight[pass_key] = max(
                self.max_in_flight.get(pass_key, 0), in_flight
            )
        try:
            await asyncio.sleep(0.05)
            return await super().analyze(pass_key=pass_key, payload=payload)
        finally:
            async with self.lock:
                self.in_flight[pass_key] -= 1


@pytest.mark.asyncio
async def test_runner_extracts_atomic_batches_concurrently_within_bound(
    distillation_data,
) -> None:
    database, tenant, _, project, source, _ = distillation_data
    async with database.session() as session:
        session.add_all(
            [
                RagChunkModel(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    source_file_id=source.id,
                    ordinal=index,
                    content=f"Concurrent source {index}",
                    content_hash=f"c{index:063d}",
                )
                for index in range(2, 15)
            ]
        )
    run = await SourceDistillationService(database).start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="concurrent-atomic",
    )
    analyzer = _SlowAtomicAnalyzer()

    result = await SourceDistillationRunner(
        database,
        analyzer,
        chunk_batch_size=1,
        evidence_batch_size=5,
        extract_concurrency=3,
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    assert result.processed_chunks == 15
    assert analyzer.max_in_flight["atomic_evidence"] == 3
    assert analyzer.max_in_flight["cross_unit_synthesis"] == 3
    assert analyzer.calls.count("atomic_evidence") == 15
    async with database.session() as session:
        stored = await session.get(type(run), run.id)
        assert stored is not None
        assert stored.pass_key == "human_decision"


class _FailingSynthesisAnalyzer(_DeterministicAnalyzer):
    def __init__(self, *, fail_group: int | None) -> None:
        super().__init__()
        self.fail_group = fail_group
        self.groups: list[int] = []

    async def analyze(self, *, pass_key: str, payload: dict[str, object]) -> dict[str, object]:
        if pass_key == "candidate_profile":
            self.calls.append(pass_key)
            return {
                "profile": {"relationship_engine": "grouped synthesis"},
                "evidence_keys": [item["evidence_key"] for item in payload["evidence"]],
                "exclusions": ["author imitation"],
                "ready_with_gaps": False,
            }
        if pass_key != "cross_unit_synthesis":
            return await super().analyze(pass_key=pass_key, payload=payload)
        group = int(payload["group"])
        self.calls.append(pass_key)
        self.groups.append(group)
        if group == self.fail_group:
            raise RuntimeError("provider interrupted")
        first = payload["evidence"][0]
        return {
            "evidence": [
                {
                    "evidence_key": f"synthesis-group-{group}",
                    "chunk_id": first["chunk_id"],
                    "source_unit": "whole-work",
                    "dimension": "relationship_state",
                    "claim": f"Synthesis group {group}",
                    "confidence": 80,
                    "inference": True,
                    "related_evidence_keys": [first["evidence_key"]],
                }
            ]
        }


@pytest.mark.asyncio
async def test_runner_resumes_cross_unit_synthesis_from_completed_group(
    distillation_data,
) -> None:
    database, tenant, _, project, source, _ = distillation_data
    async with database.session() as session:
        session.add_all(
            [
                RagChunkModel(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    source_file_id=source.id,
                    ordinal=index,
                    content=f"Additional source {index}",
                    content_hash=f"{index:064d}",
                )
                for index in range(2, 7)
            ]
        )
    service = SourceDistillationService(database)
    run = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="resume-synthesis",
    )
    failing = _FailingSynthesisAnalyzer(fail_group=1)
    runner = SourceDistillationRunner(
        database, failing, chunk_batch_size=7, evidence_batch_size=5
    )

    with pytest.raises(RuntimeError, match="provider interrupted"):
        await runner.run(tenant_id=tenant.id, distillation_id=run.id)

    async with database.session() as session:
        stored = await session.get(type(run), run.id)
        assert stored is not None
        assert stored.pass_key == "cross_unit_synthesis"
        assert stored.checkpoint["synthesis_groups_processed"] == [0]

    resumed = _FailingSynthesisAnalyzer(fail_group=None)
    result = await SourceDistillationRunner(
        database, resumed, chunk_batch_size=7, evidence_batch_size=5
    ).run(tenant_id=tenant.id, distillation_id=run.id)

    assert resumed.groups == [1]
    assert result.processed_chunks == 7
    assert result.status == "ready_with_gaps"
    async with database.session() as session:
        final = await session.get(type(run), run.id)
        assert final is not None
        assert final.checkpoint["synthesis_groups_processed"] == [0, 1]


@pytest.mark.asyncio
async def test_synthesis_persist_drops_forward_references_while_atomic_stays_strict(
    distillation_data,
) -> None:
    database, tenant, _, project, source, chunks = distillation_data
    service = SourceDistillationService(database)
    run = await service.start(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_ids=[source.id],
        idempotency_key="refs-test",
    )
    runner = SourceDistillationRunner(database, analyzer=object())
    drafts = [
        EvidenceDraft(
            evidence_key="e1",
            chunk_id=chunks[0].id,
            source_unit="u1",
            dimension="character_state",
            claim="苏晚上夜班三年",
            confidence=90,
            inference=False,
            related_evidence_keys=["not-yet-persisted-key"],
        )
    ]
    await runner._persist_drafts(tenant.id, run, drafts, strict_refs=False)
    async with database.session() as session:
        rows = (await session.scalars(select(SourceEvidenceModel))).all()
        assert len(rows) == 1
        assert rows[0].related_evidence_ids == []
    strict_draft = EvidenceDraft(
        evidence_key="e2",
        chunk_id=chunks[0].id,
        source_unit="u1",
        dimension="character_state",
        claim="另一条证据",
        confidence=90,
        inference=False,
        related_evidence_keys=["not-yet-persisted-key"],
    )
    with pytest.raises(AnalyzerOutputError, match="unknown related evidence keys"):
        await runner._persist_drafts(tenant.id, run, [strict_draft], strict_refs=True)
