import pytest

from scriptnow.platform.context_retrieval import (
    ContextRequest,
    RetrievalManifestPayload,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalStopReason,
)
from scriptnow.platform.creative_operations import (
    CreativeOperationError,
    CreativeOperationStore,
    coherent_run_status,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeArtifactRefModel,
    CreativeContextManifestModel,
    CreativeOperationModel,
    CreativeOperationStatus,
    CreativeResumptionStatus,
    CreativeStageRunModel,
    CreativeStageStatus,
    DecisionRequestStatus,
    ProjectMedium,
    ProjectModel,
    TenantModel,
)
from scriptnow.platform.retrieval_manifest import RetrievalManifestStore


@pytest.mark.parametrize(
    ("run_status", "operation_status", "expected"),
    [
        ("running", "running", "running"),
        ("succeeded", "running", "running"),
        ("succeeded", "queued", "queued"),
        ("succeeded", "waiting_for_user", "waiting_for_user"),
        ("succeeded", "succeeded", "succeeded"),
        ("succeeded", "failed", "failed"),
        ("failed", "running", "running"),
        ("failed", "failed", "failed"),
        ("cancelled", "cancelled", "cancelled"),
        ("succeeded", None, "succeeded"),
    ],
)
def test_coherent_run_status(
    run_status: str,
    operation_status: str | None,
    expected: str,
) -> None:
    assert coherent_run_status(run_status, operation_status) == expected


@pytest.fixture
async def operation_data() -> tuple[
    CreativeOperationStore, Database, TenantModel, ProjectModel
]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Story",
            medium=ProjectMedium.NOVEL,
        )
        session.add(project)
        await session.flush()
    yield CreativeOperationStore(database), database, tenant, project
    await database.dispose()


@pytest.mark.asyncio
async def test_operation_lineage_and_decision_are_durable_and_idempotent(
    operation_data: tuple[CreativeOperationStore, Database, TenantModel, ProjectModel],
) -> None:
    store, database, tenant, project = operation_data
    session_id = await store.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="novel",
    )
    turn_id = await store.append_turn(
        tenant_id=tenant.id,
        session_id=session_id,
        actor={"type": "user", "id": "writer"},
        input={"type": "command", "text": "生成第一章候选"},
    )
    operation = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=turn_id,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="turn-1:chapter-1",
        policy_snapshot={"chapter_id": "chapter-1", "target_words": 1800},
    )
    repeated = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=turn_id,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="turn-1:chapter-1",
        policy_snapshot={"chapter_id": "chapter-1", "target_words": 1800},
    )
    assert repeated == operation

    stage_id = await store.start_stage(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_key="chapter_candidate",
        attempt=1,
        input_digest="a" * 64,
    )
    checkpoint_id = await store.save_checkpoint(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        checkpoint_key="candidate-ready",
        state_format="agentscope-state-v1",
        state_payload=b"parked-state",
        resume_metadata={"reply_id": "reply-1"},
        is_complete=True,
    )
    artifact_id = await store.register_artifact(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        domain="novel",
        artifact_type="chapter_revision",
        artifact_id="revision-1",
        revision=1,
        status="candidate",
        schema_version=1,
        input_digest="a" * 64,
        dependency_versions={"story_map": 2},
        provenance={"provider": "configured-runtime", "stage": "chapter_candidate"},
    )
    decision = await store.request_decision(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        artifact_ref_id=artifact_id,
        checkpoint_id=checkpoint_id,
        kind="adopt_candidate",
        prompt="是否采纳此候选？",
        options=[{"id": "approve", "label": "采纳"}, {"id": "reject", "label": "退回"}],
        impact={"approve": "candidate becomes accepted revision"},
        idempotency_key="adopt:revision-1",
    )
    assert decision.status == DecisionRequestStatus.PENDING

    resolved = await store.resolve_decision(
        tenant_id=tenant.id,
        decision_id=decision.id,
        status=DecisionRequestStatus.APPROVED,
        decision={"option": "approve", "feedback": ""},
        decided_by={"type": "user", "id": "writer"},
    )
    repeated_resolution = await store.resolve_decision(
        tenant_id=tenant.id,
        decision_id=decision.id,
        status=DecisionRequestStatus.APPROVED,
        decision={"option": "approve", "feedback": ""},
        decided_by={"type": "user", "id": "writer"},
    )
    assert repeated_resolution.id == resolved.id
    assert repeated_resolution.status == resolved.status
    assert repeated_resolution.decision == resolved.decision
    assert resolved.decided_at is not None
    claim = await store.claim_resumption(
        tenant_id=tenant.id,
        decision_id=decision.id,
        idempotency_key="resume:revision-1",
        claimed_by={"type": "worker", "id": "worker-1"},
    )
    repeated_claim = await store.claim_resumption(
        tenant_id=tenant.id,
        decision_id=decision.id,
        idempotency_key="resume:revision-1",
        claimed_by={"type": "worker", "id": "worker-1"},
    )
    assert repeated_claim == claim
    finished_claim = await store.finish_resumption(
        tenant_id=tenant.id,
        resumption_id=claim.id,
        result={"artifact_ref_id": artifact_id},
    )
    repeated_finish = await store.finish_resumption(
        tenant_id=tenant.id,
        resumption_id=claim.id,
        result={"artifact_ref_id": artifact_id},
    )
    assert repeated_finish == finished_claim
    assert finished_claim.status == CreativeResumptionStatus.COMPLETED

    async with database.session() as db:
        stored_operation = await db.get(CreativeOperationModel, operation.id)
        stored_manifest = await db.get(
            CreativeContextManifestModel,
            stored_operation.context_manifest_id if stored_operation else None,
        )
        stored_stage = await db.get(CreativeStageRunModel, stage_id)
        stored_artifact = await db.get(CreativeArtifactRefModel, artifact_id)
        assert stored_operation is not None
        assert stored_operation.status == CreativeOperationStatus.RUNNING
        assert stored_manifest is not None
        assert stored_manifest.project_id == project.id
        assert stored_manifest.content["turn_input"]["text"] == "生成第一章候选"
        assert stored_manifest.content["operation"]["policy"]["target_words"] == 1800
        assert stored_stage is not None
        assert stored_stage.status == CreativeStageStatus.RUNNING
        assert stored_artifact is not None
        assert stored_artifact.provenance["provider"] == "configured-runtime"


@pytest.mark.asyncio
async def test_context_manifest_is_content_addressed_and_detects_tampering(
    operation_data: tuple[CreativeOperationStore, Database, TenantModel, ProjectModel],
) -> None:
    store, database, tenant, project = operation_data
    session_id = await store.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="novel",
    )
    first = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="manifest:first",
        policy_snapshot={"chapter_id": "chapter-1", "target_words": 1800},
    )
    second = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=None,
        command="novel.chapter.regenerate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="manifest:second",
        policy_snapshot={"chapter_id": "chapter-1", "target_words": 1800},
    )
    async with database.session() as db:
        first_row = await db.get(CreativeOperationModel, first.id)
        second_row = await db.get(CreativeOperationModel, second.id)
        assert first_row is not None
        assert second_row is not None
        assert first_row.context_manifest_id == second_row.context_manifest_id
        manifest = await db.get(
            CreativeContextManifestModel,
            first_row.context_manifest_id,
        )
        assert manifest is not None
        manifest.content = {**manifest.content, "tampered": True}

    async with database.session() as db:
        with pytest.raises(ValueError, match="digest does not match"):
            await store.context_manifests.load(
                db,
                tenant_id=tenant.id,
                manifest_id=first_row.context_manifest_id,
            )


@pytest.mark.asyncio
async def test_operation_context_references_matching_retrieval_manifest(
    operation_data: tuple[CreativeOperationStore, Database, TenantModel, ProjectModel],
) -> None:
    store, database, tenant, project = operation_data
    session_id = await store.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="novel",
    )
    payload = RetrievalManifestPayload(
        request=ContextRequest(
            tenant_id=tenant.id,
            project_id=project.id,
            domain="novel",
            stage="chapter_candidate",
            operation="novel.chapter.generate",
            unit_ref="chapter-1",
            required_dimensions=("continuity",),
            risk_level="normal",
            policy_ref="project-policy-v1",
        ),
        policy=RetrievalPolicy(
            allowed_sources=("project_facts",),
            retrieval_modes=(RetrievalMode.CANONICAL,),
            coverage_requirements={"continuity": 1.0},
            token_limit=4000,
            timeout_seconds=10,
            max_iterations=1,
            conflict_policy="surface",
            external_research_enabled=False,
        ),
        coverage={"continuity": 1.0},
        input_tokens=0,
        output_tokens=0,
        latency_ms=2,
        stop_reason=RetrievalStopReason.COVERAGE_MET,
    )
    async with database.session() as db:
        retrieval_manifest = await RetrievalManifestStore().create(db, payload=payload)
        retrieval_manifest_id = retrieval_manifest.id

    operation = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="with-retrieval-manifest",
        policy_snapshot={"chapter_id": "chapter-1"},
        retrieval_manifest_id=retrieval_manifest_id,
    )
    async with database.session() as db:
        operation_row = await db.get(CreativeOperationModel, operation.id)
        assert operation_row is not None
        context = await store.context_manifests.load(
            db,
            tenant_id=tenant.id,
            manifest_id=operation_row.context_manifest_id,
        )
        assert context.retrieval_manifest_id == retrieval_manifest_id
        assert context.content["retrieval_manifest"]["id"] == retrieval_manifest_id
        assert (
            context.source_versions["retrieval_manifest"]
            == context.content["retrieval_manifest"]["content_digest"]
        )

    with pytest.raises(
        CreativeOperationError,
        match="retrieval manifest does not match operation scope",
    ):
        await store.enqueue_operation(
            tenant_id=tenant.id,
            session_id=session_id,
            turn_id=None,
            run_id=None,
            command="novel.blueprint.generate",
            domain="novel",
            stage="blueprint",
            idempotency_key="mismatched-retrieval-manifest",
            policy_snapshot={},
            retrieval_manifest_id=retrieval_manifest_id,
        )


@pytest.mark.asyncio
async def test_operation_rejects_cross_tenant_and_cross_operation_references(
    operation_data: tuple[CreativeOperationStore, Database, TenantModel, ProjectModel],
) -> None:
    store, database, tenant, project = operation_data
    session_id = await store.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="novel",
    )
    operation = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="first",
        policy_snapshot={},
    )
    stage_id = await store.start_stage(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_key="chapter_candidate",
        attempt=1,
        input_digest="a" * 64,
    )
    async with database.session() as db:
        other = TenantModel(name="Other")
        db.add(other)
        await db.flush()

    with pytest.raises(CreativeOperationError, match="outside tenant scope"):
        await store.append_turn(
            tenant_id=other.id,
            session_id=session_id,
            actor={"type": "user"},
            input={"text": "attack"},
        )
    with pytest.raises(CreativeOperationError, match="must be positive"):
        await store.start_stage(
            tenant_id=tenant.id,
            operation_id=operation.id,
            stage_key="chapter_candidate",
            attempt=0,
            input_digest="a" * 64,
        )
    with pytest.raises(CreativeOperationError, match="outside operation"):
        await store.request_decision(
            tenant_id=tenant.id,
            operation_id=operation.id,
            stage_run_id=stage_id,
            artifact_ref_id="missing",
            checkpoint_id=None,
            kind="adopt_candidate",
            prompt="采纳？",
            options=[],
            impact={},
            idempotency_key="invalid-ref",
        )


@pytest.mark.asyncio
async def test_decision_cannot_be_changed_after_resolution(
    operation_data: tuple[CreativeOperationStore, Database, TenantModel, ProjectModel],
) -> None:
    store, _, tenant, project = operation_data
    session_id = await store.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="novel",
    )
    operation = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="decision-lock",
        policy_snapshot={},
    )
    stage_id = await store.start_stage(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_key="chapter_candidate",
        attempt=1,
        input_digest="a" * 64,
    )
    pending = await store.request_decision(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        artifact_ref_id=None,
        checkpoint_id=None,
        kind="continue",
        prompt="继续？",
        options=[{"id": "approve"}],
        impact={"approve": "resume"},
        idempotency_key="continue-1",
    )
    await store.resolve_decision(
        tenant_id=tenant.id,
        decision_id=pending.id,
        status=DecisionRequestStatus.APPROVED,
        decision={"option": "approve"},
        decided_by={"type": "user", "id": "writer"},
    )
    with pytest.raises(CreativeOperationError, match="already been resolved"):
        await store.resolve_decision(
            tenant_id=tenant.id,
            decision_id=pending.id,
            status=DecisionRequestStatus.REJECTED,
            decision={"option": "reject"},
            decided_by={"type": "user", "id": "writer"},
        )


@pytest.mark.asyncio
async def test_resumption_rejects_second_claim_and_unresolved_decision(
    operation_data: tuple[CreativeOperationStore, Database, TenantModel, ProjectModel],
) -> None:
    store, _, tenant, project = operation_data
    session_id = await store.open_session(
        tenant_id=tenant.id,
        project_id=project.id,
        active_domain="novel",
    )
    operation = await store.enqueue_operation(
        tenant_id=tenant.id,
        session_id=session_id,
        turn_id=None,
        run_id=None,
        command="novel.chapter.generate",
        domain="novel",
        stage="chapter_candidate",
        idempotency_key="parked-operation",
        policy_snapshot={},
    )
    stage_id = await store.start_stage(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_key="chapter_candidate",
        attempt=1,
        input_digest="b" * 64,
    )
    checkpoint_id = await store.save_checkpoint(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        checkpoint_key="parked-tool",
        state_format="agentscope-agent-state-json-v1",
        state_payload=b'{"version":1}',
        resume_metadata={"reply_id": "reply-1"},
        is_complete=True,
    )
    decision = await store.request_decision(
        tenant_id=tenant.id,
        operation_id=operation.id,
        stage_run_id=stage_id,
        artifact_ref_id=None,
        checkpoint_id=checkpoint_id,
        kind="tool_confirmation",
        prompt="允许调用工具吗？",
        options=[{"id": "approve"}, {"id": "reject"}],
        impact={"tool": "save_candidate"},
        idempotency_key="confirm-tool",
    )
    with pytest.raises(CreativeOperationError, match="must be resolved"):
        await store.claim_resumption(
            tenant_id=tenant.id,
            decision_id=decision.id,
            idempotency_key="resume-1",
            claimed_by={"type": "worker", "id": "worker-1"},
        )
    await store.resolve_decision(
        tenant_id=tenant.id,
        decision_id=decision.id,
        status=DecisionRequestStatus.APPROVED,
        decision={"approved": True},
        decided_by={"type": "user", "id": "writer"},
    )
    await store.claim_resumption(
        tenant_id=tenant.id,
        decision_id=decision.id,
        idempotency_key="resume-1",
        claimed_by={"type": "worker", "id": "worker-1"},
    )
    with pytest.raises(CreativeOperationError, match="already claimed"):
        await store.claim_resumption(
            tenant_id=tenant.id,
            decision_id=decision.id,
            idempotency_key="resume-2",
            claimed_by={"type": "worker", "id": "worker-2"},
        )
