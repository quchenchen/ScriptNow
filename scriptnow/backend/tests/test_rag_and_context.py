import pytest
from sqlalchemy import select

from scriptnow.platform.context_retrieval import (
    ContextRequest,
    RetrievalMode,
    RetrievalPolicy,
    RetrievalQuery,
)
from scriptnow.platform.context_summary import ContextSummary
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    RagChunkModel,
    SourceDistillationModel,
    SourceEvidenceModel,
    TenantModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)
from scriptnow.platform.rag import RagError, RagService
from scriptnow.platform.retrievers import LexicalRagRetriever


@pytest.fixture
async def rag_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Adaptation", medium=ProjectMedium.NOVEL)
        session.add(project)
        await session.flush()
        source = WorkspaceFileModel(
            tenant_id=tenant.id,
            project_id=project.id,
            original_name="source.txt",
            storage_name="random.txt",
            media_type="text/plain",
            byte_size=20,
            sha256="0" * 64,
            status=WorkspaceFileStatus.READY,
        )
        session.add(source)
        await session.flush()
    yield RagService(database, chunk_characters=100), tenant, other, project, source
    await database.dispose()


@pytest.mark.asyncio
async def test_rag_reindex_search_and_tenant_isolation(rag_data) -> None:
    rag, tenant, other, project, source = rag_data
    assert (
        await rag.index_text(
            tenant_id=tenant.id,
            project_id=project.id,
            source_file_id=source.id,
            parsed_text="Harbor fog hides the witness. " * 8,
        )
        == 3
    )
    hits = await rag.search(tenant_id=tenant.id, project_id=project.id, query="harbor witness")
    assert hits and hits[0].score >= 2
    assert await rag.search(tenant_id=other.id, project_id=project.id, query="harbor") == []
    with pytest.raises(RagError, match="tenant workspace"):
        await rag.index_text(
            tenant_id=other.id,
            project_id=project.id,
            source_file_id=source.id,
            parsed_text="poison",
        )
    assert (
        await rag.index_text(
            tenant_id=tenant.id,
            project_id=project.id,
            source_file_id=source.id,
            parsed_text="Mountain snow replaces every harbor reference.",
        )
        == 1
    )
    assert await rag.search(tenant_id=tenant.id, project_id=project.id, query="witness") == []


@pytest.mark.asyncio
async def test_lexical_retriever_preserves_source_version_and_explicit_dimensions(
    rag_data,
) -> None:
    rag, tenant, _, project, source = rag_data
    await rag.index_text(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_id=source.id,
        parsed_text="Harbor fog hides the witness.",
    )
    retriever = LexicalRagRetriever(
        rag,
        source_type="uploaded_source",
        result_limit=3,
        token_counter=lambda text: len(text.split()),
    )
    request = ContextRequest(
        tenant_id=tenant.id,
        project_id=project.id,
        domain="novel",
        stage="chapter_candidate",
        operation="novel.chapter_candidate.generate",
        required_dimensions=("character", "continuity"),
        risk_level="normal",
        policy_ref="test-policy",
    )
    policy = RetrievalPolicy(
        allowed_sources=("uploaded_source",),
        retrieval_modes=(RetrievalMode.LEXICAL,),
        coverage_requirements={"continuity": 1.0},
        token_limit=500,
        timeout_seconds=5,
        max_iterations=1,
        conflict_policy="surface",
        external_research_enabled=False,
    )
    batch = await retriever.retrieve(
        request,
        policy,
        RetrievalQuery(
            query="harbor witness",
            iteration=1,
            mode=RetrievalMode.LEXICAL,
            purpose="retrieve continuity evidence",
            dimensions=("continuity",),
        ),
    )

    assert len(batch.evidence) == 1
    assert batch.evidence[0].dimensions == ("continuity",)
    assert batch.evidence[0].source_version == f"sha256:{source.sha256}"
    assert batch.evidence[0].content_digest
    assert batch.evidence[0].excerpt == "Harbor fog hides the witness."


@pytest.mark.asyncio
async def test_reindex_preserves_chunks_referenced_by_evidence(rag_data) -> None:
    rag, tenant, _, project, source = rag_data
    await rag.index_text(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_id=source.id,
        parsed_text="Harbor fog hides the witness. " * 8,
    )
    async with rag.database.session() as session:
        chunk = (
            await session.scalars(
                select(RagChunkModel).where(
                    RagChunkModel.source_file_id == source.id
                )
            )
        ).first()
        assert chunk is not None
        distillation = SourceDistillationModel(
            tenant_id=tenant.id,
            project_id=project.id,
            idempotency_key="rag-reindex-distill",
            source_file_ids=[source.id],
            status="running",
            pass_key="atomic_evidence",
        )
        session.add(distillation)
        await session.flush()
        session.add(
            SourceEvidenceModel(
                tenant_id=tenant.id,
                project_id=project.id,
                distillation_id=distillation.id,
                evidence_key="evidence-refs-chunk",
                source_file_id=source.id,
                chunk_id=chunk.id,
                source_unit="chapter-1",
                ordinal=chunk.ordinal,
                dimension="character_state",
                claim="The chunk carries distillation evidence.",
                confidence=90,
                extraction_pass="atomic_evidence",
            )
        )

    await rag.index_text(
        tenant_id=tenant.id,
        project_id=project.id,
        source_file_id=source.id,
        parsed_text="Mountain snow replaces every harbor reference.",
    )

    async with rag.database.session() as session:
        referenced = (
            await session.scalars(
                select(SourceEvidenceModel).where(
                    SourceEvidenceModel.evidence_key == "evidence-refs-chunk"
                )
            )
        ).one()
        preserved = await session.get(RagChunkModel, referenced.chunk_id)
        assert preserved is not None
        assert "Harbor fog" in preserved.content
        assert "Mountain snow" not in preserved.content


@pytest.mark.asyncio
async def test_lexical_retriever_searches_explicit_source_project(rag_data) -> None:
    rag, tenant, _, project, _ = rag_data
    async with rag.database.session() as session:
        source_project = ProjectModel(
            tenant_id=tenant.id,
            name="Source manuscript",
            medium=ProjectMedium.NOVEL,
        )
        session.add(source_project)
        await session.flush()
        source_file = WorkspaceFileModel(
            tenant_id=tenant.id,
            project_id=source_project.id,
            original_name="source-manuscript.txt",
            storage_name="source-manuscript.txt",
            media_type="text/plain",
            byte_size=40,
            sha256="1" * 64,
            status=WorkspaceFileStatus.READY,
        )
        session.add(source_file)
        await session.flush()
    await rag.index_text(
        tenant_id=tenant.id,
        project_id=source_project.id,
        source_file_id=source_file.id,
        parsed_text="The silver witness remembers the sealed harbor.",
    )
    retriever = LexicalRagRetriever(
        rag,
        source_type="uploaded_source",
        result_limit=3,
        token_counter=lambda text: len(text.split()),
    )
    request = ContextRequest(
        tenant_id=tenant.id,
        project_id=project.id,
        retrieval_project_ids=(source_project.id,),
        domain="translation",
        stage="chapter_translation",
        operation="faithful_translate",
        required_dimensions=("source_fidelity",),
        risk_level="high",
        policy_ref="test-source-project-policy",
    )
    batch = await retriever.retrieve(
        request,
        RetrievalPolicy(
            allowed_sources=("uploaded_source",),
            retrieval_modes=(RetrievalMode.LEXICAL,),
            coverage_requirements={"source_fidelity": 0.5},
            token_limit=500,
            timeout_seconds=5,
            max_iterations=1,
            conflict_policy="surface",
            external_research_enabled=False,
        ),
        RetrievalQuery(
            query="silver witness",
            iteration=1,
            mode=RetrievalMode.LEXICAL,
            purpose="retrieve source evidence",
            dimensions=("source_fidelity",),
        ),
    )

    assert len(batch.evidence) == 1
    assert batch.evidence[0].source_id == source_file.id


def test_context_compression_contract_requires_three_preserved_categories() -> None:
    summary = ContextSummary.validate(
        {
            "creative_decisions": ["The witness lies"],
            "user_preferences": ["restrained dialogue"],
            "forbidden_terms": ["destiny"],
            "narrative_summary": "Act one closes at the harbor.",
        }
    )
    assert summary.creative_decisions == ("The witness lies",)
    with pytest.raises(ValueError, match="must preserve"):
        ContextSummary.validate({"creative_decisions": []})
