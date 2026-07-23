from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from scriptflow_v6.db import session_factory
from scriptflow_v6.manuscript_documents import (
    get_document,
    list_document_versions,
    restore_document_version,
    save_document,
)
from scriptflow_v6.models import ManuscriptUnit, Project, User
from scriptflow_v6.projects import create_project
from scriptflow_v6.schemas import CreateProject, RestoreManuscriptDocument, SaveManuscriptDocument


async def create_adopted_unit(db) -> tuple[Project, User, ManuscriptUnit]:
    project_view = await create_project(db, CreateProject(title="可编辑正文", goal_type="original-novel"))
    project = await db.get(Project, project_view.id)
    owner = await db.scalar(select(User).where(User.id == project.owner_id))
    unit = ManuscriptUnit(
        project_id=project.id,
        unit_type="chapter",
        ordinal=1,
        title="第一章",
        adopted_content="第一版正文",
        status="adopted",
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return project, owner, unit


@pytest.mark.asyncio
async def test_direct_edit_creates_version_history_and_updates_adopted_content():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        baseline = await get_document(db, project.id, unit.id, owner.id)
        assert baseline.version == 1
        assert baseline.source == "adopted_baseline"
        assert baseline.metadata["narrative_person"] == "第三人称"

        saved = await save_document(
            db, project.id, unit.id, owner.id,
            SaveManuscriptDocument(base_version=1, content="创作者直接修改后的正文"),
        )
        assert saved.version == 2
        assert saved.source == "manual_edit"
        await db.refresh(unit)
        assert unit.adopted_content == "创作者直接修改后的正文"
        versions = await list_document_versions(db, project.id, unit.id, owner.id)
        assert [version.version for version in versions] == [2, 1]


@pytest.mark.asyncio
async def test_professional_metadata_is_versioned_with_chapter_content():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        await get_document(db, project.id, unit.id, owner.id)
        saved = await save_document(
            db, project.id, unit.id, owner.id,
            SaveManuscriptDocument(
                base_version=1,
                content="第一版正文",
                metadata={"pov_character": "二丫", "narrative_person": "第一人称", "time_position": "三小时后"},
            ),
        )
        assert saved.version == 2
        assert saved.metadata == {
            "pov_character": "二丫", "narrative_person": "第一人称", "time_position": "三小时后",
        }
        versions = await list_document_versions(db, project.id, unit.id, owner.id)
        assert versions[0].metadata["pov_character"] == "二丫"
        assert versions[1].metadata["pov_character"] == ""


@pytest.mark.asyncio
async def test_direct_edit_rejects_stale_base_without_overwriting_current_content():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        await get_document(db, project.id, unit.id, owner.id)
        await save_document(
            db, project.id, unit.id, owner.id,
            SaveManuscriptDocument(base_version=1, content="第二版"),
        )
        with pytest.raises(HTTPException) as stale:
            await save_document(
                db, project.id, unit.id, owner.id,
                SaveManuscriptDocument(base_version=1, content="过期编辑"),
            )
        assert stale.value.status_code == 409
        await db.refresh(unit)
        assert unit.adopted_content == "第二版"


@pytest.mark.asyncio
async def test_restore_creates_a_new_version_instead_of_erasing_history():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        await get_document(db, project.id, unit.id, owner.id)
        await save_document(
            db, project.id, unit.id, owner.id,
            SaveManuscriptDocument(base_version=1, content="第二版正文"),
        )
        restored = await restore_document_version(
            db, project.id, unit.id, owner.id,
            RestoreManuscriptDocument(base_version=2, restore_version=1),
        )
        assert restored.version == 3
        assert restored.content == "第一版正文"
        assert restored.source == "restore_v1"
        versions = await list_document_versions(db, project.id, unit.id, owner.id)
        assert [version.version for version in versions] == [3, 2, 1]
