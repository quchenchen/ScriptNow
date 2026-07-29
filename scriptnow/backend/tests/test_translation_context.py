from __future__ import annotations

import pytest

from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.platform.context_retrieval import (
    ContextRequest,
    RetrievalMode,
    RetrievalPolicy,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    TenantModel,
    new_id,
)
from scriptnow.translation.context import FaithfulTranslationContextAdapter
from scriptnow.translation.domain import TranslationGlossaryTermModel


@pytest.mark.asyncio
async def test_translation_context_uses_source_revision_and_confirmed_glossary() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        session.add(tenant)
        await session.flush()
        source = ProjectModel(
            tenant_id=tenant.id,
            name="Source",
            medium=ProjectMedium.NOVEL,
        )
        session.add(source)
        await session.flush()
        translation = ProjectModel(
            tenant_id=tenant.id,
            name="Translation",
            medium=ProjectMedium.TRANSLATION,
            direction={
                "source_project_id": source.id,
                "source_language": "zh-CN",
                "target_language": "en-US",
            },
        )
        session.add(translation)
        await session.flush()
        session.add(
            NovelStoryMapModel(
                project_id=source.id,
                version=3,
                volumes=[
                    {
                        "id": "volume-1",
                        "chapters": [{"id": "chapter-1", "title": "第一章"}],
                    }
                ],
            )
        )
        source_revision = NovelDocumentRevisionModel(
            project_id=source.id,
            chapter_id="chapter-1",
            revision_number=2,
            blocks=[{"type": "prose", "text": "雨一路跟她回家。"}],
            status=NovelRevisionStatus.ADOPTED,
            idempotency_key="source-v2",
        )
        session.add(source_revision)
        session.add(
            TranslationGlossaryTermModel(
                id=new_id(),
                project_id=translation.id,
                source_term="月契",
                target_term="Moon Bond",
                status="confirmed",
            )
        )
        await session.flush()

    request = ContextRequest(
        tenant_id=tenant.id,
        project_id=translation.id,
        domain="translation",
        stage="chapter_translation",
        operation="translation.chapter.generate",
        unit_ref="chapter-1",
        required_dimensions=(
            "source_fidelity",
            "terminology",
            "voice",
            "continuity",
        ),
        risk_level="normal",
        policy_ref="translation-context-v1",
    )
    policy = RetrievalPolicy(
        allowed_sources=(
            "source_revision",
            "translation_glossary",
            "prior_translation",
        ),
        retrieval_modes=(RetrievalMode.CANONICAL,),
        coverage_requirements={
            "source_fidelity": 1.0,
            "terminology": 1.0,
            "voice": 1.0,
            "continuity": 1.0,
        },
        token_limit=8000,
        timeout_seconds=10,
        max_iterations=1,
        conflict_policy="surface",
        external_research_enabled=False,
    )

    seed = await FaithfulTranslationContextAdapter(
        database,
        token_counter=lambda value: len(value.split()),
    ).canonical_context(request, policy)

    assert seed.coverage == {
        "source_fidelity": 1.0,
        "voice": 1.0,
        "terminology": 1.0,
        "continuity": 1.0,
    }
    assert seed.domain_state == {
        "source_project_id": source.id,
        "chapter_ordinal": 1,
        "chapter_count": 1,
    }
    assert seed.canonical_facts == (
        {
            "kind": "confirmed_glossary",
            "terms": [{"source": "月契", "target": "Moon Bond"}],
        },
    )
    assert {item.source_type for item in seed.evidence} == {
        "source_revision",
        "translation_glossary",
    }
    assert "version:3" in seed.source_versions.values()
    await database.dispose()
