from __future__ import annotations

import pytest
from pydantic import ValidationError

from scriptnow.platform.context_retrieval import (
    ContextRequest,
    EvidenceRef,
    RetrievalManifestPayload,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
    RetrievalStopReason,
)
from scriptnow.platform.context_retrieval_service import ContextRetrievalService
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeRetrievalManifestModel,
    ProjectMedium,
    ProjectModel,
    TenantModel,
)
from scriptnow.platform.retrieval_kernel import ContextSeed, RetrievalCoordinator
from scriptnow.platform.retrieval_manifest import RetrievalManifestStore


def retrieval_payload(
    *,
    tenant_id: str = "tenant-1",
    project_id: str = "project-1",
    domain: str = "novel",
    stage: str = "chapter_candidate",
) -> RetrievalManifestPayload:
    evidence = EvidenceRef(
        ref_id="source:1",
        source_type="uploaded_source",
        source_id="source-file-1",
        source_version="sha256:source-v1",
        locator={"chunk": 1},
        content_digest="a" * 64,
        score=0.91,
        retrieval_modes=(RetrievalMode.LEXICAL,),
    )
    return RetrievalManifestPayload(
        request=ContextRequest(
            tenant_id=tenant_id,
            project_id=project_id,
            domain=domain,
            stage=stage,
            operation=f"{domain}.{stage}.generate",
            unit_ref="chapter-1",
            user_intent="generate a candidate",
            required_dimensions=("character", "continuity"),
            risk_level="normal",
            policy_ref="project-policy-v1",
        ),
        policy=RetrievalPolicy(
            allowed_sources=("project_facts", "uploaded_source"),
            retrieval_modes=(RetrievalMode.CANONICAL, RetrievalMode.LEXICAL),
            coverage_requirements={"character": 1.0, "continuity": 0.8},
            token_limit=8000,
            timeout_seconds=20,
            max_iterations=3,
            conflict_policy="surface",
            external_research_enabled=False,
        ),
        source_versions={"uploaded_source:source-file-1": "sha256:source-v1"},
        queries=(
            RetrievalQuery(
                query="chapter one character continuity",
                iteration=1,
                mode=RetrievalMode.LEXICAL,
                purpose="fill required dimensions",
                dimensions=("character", "continuity"),
            ),
        ),
        hit_refs=(evidence,),
        coverage={"character": 1.0, "continuity": 0.9},
        input_tokens=120,
        output_tokens=0,
        latency_ms=18,
        stop_reason=RetrievalStopReason.COVERAGE_MET,
    )


def test_retrieval_contract_is_strict_immutable_and_json_round_trippable() -> None:
    payload = retrieval_payload()
    serialized = payload.model_dump(mode="json")
    assert RetrievalManifestPayload.model_validate(serialized) == payload
    with pytest.raises(ValidationError):
        ContextRequest.model_validate(
            {
                **payload.request.model_dump(),
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError):
        payload.request.stage = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        RetrievalPolicy(
            allowed_sources=("project_facts",),
            retrieval_modes=(RetrievalMode.CANONICAL,),
            token_limit=0,
            timeout_seconds=20,
            max_iterations=1,
            conflict_policy="surface",
            external_research_enabled=False,
        )
    with pytest.raises(ValidationError, match="required dimensions must be unique"):
        ContextRequest.model_validate(
            {
                **payload.request.model_dump(),
                "required_dimensions": ("character", "character"),
            }
        )
    with pytest.raises(ValidationError, match="query dimensions must be unique"):
        RetrievalQuery(
            query="characters",
            iteration=1,
            mode=RetrievalMode.LEXICAL,
            purpose="character continuity",
            dimensions=("character", "character"),
        )


@pytest.mark.asyncio
async def test_retrieval_manifest_is_content_addressed_and_detects_tampering() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    store = RetrievalManifestStore()
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
        payload = retrieval_payload(tenant_id=tenant.id, project_id=project.id)
        first = await store.create(session, payload=payload)
        second = await store.create(session, payload=payload)
        assert first.id == second.id
        manifest_id = first.id

    async with database.session() as session:
        view = await store.load(
            session,
            tenant_id=tenant.id,
            manifest_id=manifest_id,
        )
        assert view.content["stop_reason"] == "coverage_met"
        row = await session.get(CreativeRetrievalManifestModel, manifest_id)
        assert row is not None
        row.content = {**row.content, "tampered": True}

    async with database.session() as session:
        with pytest.raises(ValueError, match="digest does not match"):
            await store.load(
                session,
                tenant_id=tenant.id,
                manifest_id=manifest_id,
            )
    await database.dispose()


@pytest.mark.asyncio
async def test_retrieval_service_persists_manifest_before_runtime_use() -> None:
    class Adapter:
        domain = "novel"

        async def canonical_context(self, request, policy):
            return ContextSeed(
                task_contract={"operation": request.operation},
                coverage={"character": 1.0, "continuity": 1.0},
            )

        def plan_queries(self, request, policy, *, missing_dimensions, iteration):
            return ()

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
        payload = retrieval_payload(tenant_id=tenant.id, project_id=project.id)

    service = ContextRetrievalService(database, RetrievalCoordinator(()))
    persisted = await service.build(
        request=payload.request,
        policy=payload.policy,
        adapter=Adapter(),
    )

    async with database.session() as session:
        row = await session.get(CreativeRetrievalManifestModel, persisted.manifest_id)
        assert row is not None
        assert row.content_digest == persisted.content_digest
        assert row.content["stop_reason"] == "coverage_met"
    await database.dispose()
