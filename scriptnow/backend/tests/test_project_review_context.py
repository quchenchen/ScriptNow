import pytest
from sqlalchemy import select

from scriptnow.dock.service import DockService
from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.novel.project import NovelStoryMapModel, initialize_novel_project
from scriptnow.platform.active_runs import ActiveRunRegistry
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectMedium, ProjectModel, TenantModel
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import RevisionStatus, ScriptDocumentRevisionModel
from scriptnow.script.project import ScriptStoryMapModel, initialize_script_project


@pytest.fixture
async def review_projects():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Review Context Studio")
        session.add(tenant)
        await session.flush()
        novel = ProjectModel(
            tenant_id=tenant.id,
            name="可评审小说",
            medium=ProjectMedium.NOVEL,
            direction={"language": "zh-CN", "premise": "一封信改变了她的选择。"},
        )
        script = ProjectModel(
            tenant_id=tenant.id,
            name="可评审剧本",
            medium=ProjectMedium.SCRIPT,
            direction={"language": "zh-CN", "script_format": "chinese"},
        )
        session.add_all([novel, script])
        await session.flush()
        await initialize_novel_project(session, novel)
        await initialize_script_project(session, script)

        novel_map = (
            await session.scalars(
                select(NovelStoryMapModel).where(
                    NovelStoryMapModel.project_id == novel.id
                )
            )
        ).one()
        novel_map.volumes = [
            {
                "id": "volume-1",
                "title": "第一卷",
                "chapters": [
                    {"id": "chapter-1", "title": "来信"},
                    {"id": "chapter-2", "title": "回声"},
                ],
            }
        ]
        script_map = (
            await session.scalars(
                select(ScriptStoryMapModel).where(
                    ScriptStoryMapModel.project_id == script.id
                )
            )
        ).one()
        script_map.episodes = [
            {
                "id": "episode-1",
                "title": "第一集",
                "scenes": [{"id": "scene-1", "title": "雨夜走廊"}],
            }
        ]
        session.add_all(
            [
                NovelDocumentRevisionModel(
                    project_id=novel.id,
                    chapter_id="chapter-1",
                    revision_number=2,
                    blocks=[
                        NovelBlock(
                            block_id="novel-prose",
                            type="prose",
                            text="她在雨声里拆开那封迟到十年的信。",
                        ).model_dump(mode="json")
                    ],
                    status=NovelRevisionStatus.ADOPTED,
                    idempotency_key="review-novel-chapter-1",
                ),
                ScriptDocumentRevisionModel(
                    project_id=script.id,
                    scene_id="scene-1",
                    revision_number=1,
                    blocks=[
                        ScriptBlock(
                            para_id="script-action",
                            type="action",
                            text="△ 她停在走廊尽头，信封从手中滑落。",
                        ).model_dump(mode="json")
                    ],
                    status=RevisionStatus.ADOPTED,
                    idempotency_key="review-script-scene-1",
                ),
            ]
        )
    yield database, tenant, novel, script
    await database.dispose()


@pytest.mark.asyncio
async def test_project_reviewer_receives_adopted_novel_text_and_reports_partial_coverage(
    review_projects,
) -> None:
    database, tenant, novel, _ = review_projects
    service = DockService(database, Settings(), ActiveRunRegistry())

    context = await service.review_context(
        tenant_id=tenant.id,
        project_id=novel.id,
    )

    evidence = context["evidence_manifest"]
    assert evidence["scope"] == "whole_project"
    assert evidence["coverage"] == "partial"
    assert evidence["included_unit_ids"] == ["chapter-1"]
    assert evidence["omitted_unit_ids"] == ["chapter-2"]
    assert evidence["project_direction"]["premise"] == "一封信改变了她的选择。"
    assert evidence["documents"][0]["title"] == "来信"
    assert (
        evidence["documents"][0]["blocks"][0]["text"]
        == "她在雨声里拆开那封迟到十年的信。"
    )


@pytest.mark.asyncio
async def test_project_reviewer_receives_complete_adopted_script_text(
    review_projects,
) -> None:
    database, tenant, _, script = review_projects
    service = DockService(database, Settings(), ActiveRunRegistry())

    context = await service.review_context(
        tenant_id=tenant.id,
        project_id=script.id,
    )

    evidence = context["evidence_manifest"]
    assert evidence["coverage"] == "complete"
    assert evidence["included_unit_ids"] == ["scene-1"]
    assert evidence["omitted_unit_ids"] == []
    assert evidence["documents"][0]["title"] == "雨夜走廊"
    assert (
        evidence["documents"][0]["blocks"][0]["text"]
        == "△ 她停在走廊尽头，信封从手中滑落。"
    )
