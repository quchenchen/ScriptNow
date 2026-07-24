import pytest

from scriptnow.platform.context_summary import ContextSummary
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    TenantModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)
from scriptnow.platform.rag import RagError, RagService


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
