from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from scriptflow_v6.db import session_factory
from scriptflow_v6.main import app
from scriptflow_v6.manuscript_documents import get_document, save_document
from scriptflow_v6.manuscript_edits import (
    create_edit,
    persist_prepared_edit,
    prepare_edit,
    resolve_edit,
)
from scriptflow_v6.manuscript_impacts import list_impact_candidates
from scriptflow_v6.models import ManuscriptEditRevision, ManuscriptUnit, Project, User
from scriptflow_v6.projects import create_project
from scriptflow_v6.schemas import CreateManuscriptAiEdit, CreateProject, SaveManuscriptDocument


async def create_adopted_unit(db) -> tuple[Project, User, ManuscriptUnit]:
    project_view = await create_project(db, CreateProject(title="AI 编辑正文", goal_type="original-novel"))
    project = await db.get(Project, project_view.id)
    owner = await db.scalar(select(User).where(User.id == project.owner_id))
    unit = ManuscriptUnit(
        project_id=project.id, unit_type="chapter", ordinal=1, title="第一章",
        adopted_content="第一版正文", status="adopted",
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return project, owner, unit


@pytest.mark.asyncio
async def test_ai_selection_edit_stays_candidate_until_adopted():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        document = await get_document(db, project.id, unit.id, owner.id)
        selected = "第一版正文"
        revision = await create_edit(
            db, project.id, unit.id, owner.id,
            CreateManuscriptAiEdit(
                base_version=document.version,
                selection_start=0,
                selection_end=len(selected),
                selected_text=selected,
                mode="shorten",
                preserve=["事实", "人物语气"],
            ),
        )
        assert revision.status == "candidate"
        assert revision.replacement_text != selected
        assert (await get_document(db, project.id, unit.id, owner.id)).content == selected

        adopted = await resolve_edit(db, project.id, revision.id, owner.id, "adopt")
        assert adopted.status == "adopted"
        updated = await get_document(db, project.id, unit.id, owner.id)
        assert updated.version == 2
        assert updated.content == revision.replacement_text


@pytest.mark.asyncio
async def test_stream_preparation_can_be_discarded_without_candidate_or_document_change():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        document = await get_document(db, project.id, unit.id, owner.id)
        command = CreateManuscriptAiEdit(
            base_version=document.version,
            selection_start=0,
            selection_end=len(document.content),
            selected_text=document.content,
            mode="expand",
        )
        prepared = await prepare_edit(db, project.id, unit.id, owner.id, command)
        assert prepared["draft"].replacement_text
        assert await db.scalar(select(ManuscriptEditRevision)) is None
        assert (await get_document(db, project.id, unit.id, owner.id)).content == document.content

        candidate = await persist_prepared_edit(db, project.id, unit.id, owner.id, command, prepared)
        assert candidate.status == "candidate"
        assert (await get_document(db, project.id, unit.id, owner.id)).content == document.content


@pytest.mark.asyncio
async def test_stream_endpoint_finishes_with_persisted_candidate_and_keeps_document_unchanged():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        document = await get_document(db, project.id, unit.id, owner.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/projects/{project.id}/manuscript/units/{unit.id}/ai-edits/stream",
            json={
                "base_version": document.version,
                "selection_start": 0,
                "selection_end": len(document.content),
                "selected_text": document.content,
                "mode": "expand",
                "instruction": "增加一个克制的动作",
                "preserve": ["事实"],
            },
        )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "started"
    assert any(event["type"] == "delta" for event in events)
    assert events[-1]["type"] == "candidate"
    assert events[-1]["revision"]["status"] == "candidate"
    async with session_factory() as db:
        unchanged = await get_document(db, project.id, unit.id, owner.id)
        assert unchanged.content == document.content

@pytest.mark.asyncio
async def test_ai_selection_edit_becomes_stale_after_manual_save():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        document = await get_document(db, project.id, unit.id, owner.id)
        revision = await create_edit(
            db, project.id, unit.id, owner.id,
            CreateManuscriptAiEdit(
                base_version=1,
                selection_start=0,
                selection_end=len(document.content),
                selected_text=document.content,
                mode="polish",
            ),
        )
        await save_document(
            db, project.id, unit.id, owner.id,
            SaveManuscriptDocument(base_version=1, content="人工先修改了正文"),
        )
        with pytest.raises(HTTPException) as stale:
            await resolve_edit(db, project.id, revision.id, owner.id, "adopt")
        assert stale.value.status_code == 409


@pytest.mark.asyncio
async def test_adopted_ai_edit_creates_reviewable_continuity_impact_only_when_detected():
    async with session_factory() as db:
        project, owner, unit = await create_adopted_unit(db)
        document = await get_document(db, project.id, unit.id, owner.id)
        revision = await create_edit(
            db, project.id, unit.id, owner.id,
            CreateManuscriptAiEdit(
                base_version=1,
                selection_start=0,
                selection_end=len(document.content),
                selected_text=document.content,
                mode="custom",
                instruction="让角色得知真相并改变当前目标",
            ),
        )
        assert await list_impact_candidates(db, project.id, owner.id) == []
        await resolve_edit(db, project.id, revision.id, owner.id, "adopt")
        impacts = await list_impact_candidates(db, project.id, owner.id)
        assert len(impacts) == 1
        assert impacts[0].impact_type == "character_state"
        assert impacts[0].status == "candidate"
