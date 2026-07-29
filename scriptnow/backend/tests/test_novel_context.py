from unittest.mock import AsyncMock

import pytest

from scriptnow.novel.context import NovelChapterContextAdapter
from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.platform.context_retrieval import (
    ContextRequest,
    RetrievalMode,
    RetrievalPolicy,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectMedium, ProjectModel, TenantModel


@pytest.mark.asyncio
async def test_novel_context_uses_prior_effective_revision_and_ignores_orphans() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Novel Studio")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Novel",
            medium=ProjectMedium.NOVEL,
            direction={"language": "en-US"},
        )
        session.add(project)
        await session.flush()
        session.add(
            NovelStoryMapModel(
                project_id=project.id,
                version=4,
                volumes=[
                    {
                        "id": "volume-1",
                        "chapters": [
                            {"id": "chapter-1", "title": "Before"},
                            {"id": "chapter-2", "title": "Now"},
                        ],
                    }
                ],
            )
        )
        await session.flush()

    adapter = NovelChapterContextAdapter(
        database,
        token_counter=lambda value: len(value.split()),
    )
    adapter._service.context_pack = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "anchors": [{"id": "hero", "kind": "character", "name": "Sera"}],
            "effective_chapters": [
                {
                    "chapter_id": "chapter-1",
                    "revision_id": "manual-v3",
                    "revision_number": 3,
                    "source": "manual",
                    "blocks": [{"type": "prose", "text": "Latest author revision."}],
                },
                {
                    "chapter_id": "removed-chapter",
                    "revision_id": "orphan-v1",
                    "revision_number": 1,
                    "source": "agent",
                    "blocks": [{"type": "prose", "text": "Stale orphan."}],
                },
            ],
        }
    )
    request = ContextRequest(
        tenant_id=tenant.id,
        project_id=project.id,
        domain="novel",
        stage="chapter_writing",
        operation="novel.chapter.generate",
        unit_ref="chapter-2",
        required_dimensions=(
            "chapter_contract",
            "blueprint",
            "continuity",
            "character_state",
        ),
        risk_level="normal",
        policy_ref="novel-context-v1",
    )
    policy = RetrievalPolicy(
        allowed_sources=("novel_story_map", "novel_blueprint", "novel_revision"),
        retrieval_modes=(RetrievalMode.CANONICAL,),
        coverage_requirements={
            "chapter_contract": 1.0,
            "blueprint": 1.0,
            "continuity": 1.0,
            "character_state": 1.0,
        },
        token_limit=8000,
        timeout_seconds=10,
        max_iterations=1,
        conflict_policy="surface",
        external_research_enabled=False,
    )

    seed = await adapter.canonical_context(request, policy)

    assert seed.coverage == {
        "chapter_contract": 1.0,
        "blueprint": 1.0,
        "character_state": 1.0,
        "continuity": 1.0,
    }
    assert [item["revision_id"] for item in seed.latest_revisions] == ["manual-v3"]
    assert all("orphan-v1" not in item.ref_id for item in seed.evidence)
    assert seed.domain_state["chapter_ordinal"] == 2
    await database.dispose()
