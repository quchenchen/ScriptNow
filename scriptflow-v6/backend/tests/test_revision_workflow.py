from __future__ import annotations

import os

os.environ["SCRIPTFLOW_V6_DB_PATH"] = "/tmp/scriptflow-v6-test.db"

import pytest
from fastapi import HTTPException

from scriptflow_v6.db import session_factory
from scriptflow_v6.living_assets import list_candidates, resolve_candidate
from scriptflow_v6.models import CreativeRevision, Project, Scene, User
from scriptflow_v6.revisions import create, resolve
from scriptflow_v6.schemas import CreateRevision, RevisionBrief


async def seed():
    async with session_factory() as db:
        user = User(public_id="alice", display_name="Alice")
        db.add(user)
        await db.flush()
        project = Project(owner_id=user.id, title="雾港来信")
        db.add(project)
        await db.flush()
        scene = Scene(project_id=project.id, scene_key="EP01-SC03", adopted_content="原始对白")
        db.add(scene)
        await db.commit()
        return project.id, scene.id


@pytest.mark.asyncio
async def test_candidate_does_not_overwrite_until_adopted():
    project_id, scene_id = await seed()
    async with session_factory() as db:
        command = CreateRevision(scene_id=scene_id, candidate_content="候选对白", brief=RevisionBrief(goal="改善对白"))
        candidate = await create(db, project_id, command)
        scene = await db.get(Scene, scene_id)
        assert scene.adopted_content == "原始对白"
        adopted = await resolve(db, project_id, candidate.id, "adopt")
        assert adopted.status == "adopted"
        await db.refresh(scene)
        assert scene.adopted_content == "候选对白"


@pytest.mark.asyncio
async def test_changed_base_becomes_stale():
    project_id, scene_id = await seed()
    async with session_factory() as db:
        command = CreateRevision(scene_id=scene_id, candidate_content="候选对白", brief=RevisionBrief(goal="改善对白"))
        candidate = await create(db, project_id, command)
        scene = await db.get(Scene, scene_id)
        scene.adopted_content = "用户继续编辑"
        await db.commit()
        with pytest.raises(HTTPException, match="基线内容已变化"):
            await resolve(db, project_id, candidate.id, "adopt")
        revision = await db.get(CreativeRevision, candidate.id)
        assert revision.status == "stale"


@pytest.mark.asyncio
async def test_revision_extracts_living_asset_candidate_for_separate_decision():
    project_id, scene_id = await seed()
    async with session_factory() as db:
        command = CreateRevision(
            scene_id=scene_id,
            candidate_content="两人不再互相信任",
            brief=RevisionBrief(goal="强化人物关系破裂"),
        )
        revision = await create(db, project_id, command)
        candidates = await list_candidates(db, project_id)
        extracted = next(item for item in candidates if item.revision_id == revision.id)
        assert extracted.asset_type == "relationship_change"
        assert extracted.status == "candidate"

        with pytest.raises(HTTPException, match="先采用对应的正文 Revision"):
            await resolve_candidate(db, project_id, extracted.id, "adopt")
        await resolve(db, project_id, revision.id, "adopt")
        # 关系物化要求两个已采用实体；此 fixture 没有 Story Core，先验证独立拒绝路径。
        rejected = await resolve_candidate(db, project_id, extracted.id, "reject")
        assert rejected.status == "rejected"

        command = CreateRevision(scene_id=scene_id, candidate_content="新线索", brief=RevisionBrief(goal="埋下邮戳伏笔"))
        clue_revision = await create(db, project_id, command)
        await resolve(db, project_id, clue_revision.id, "adopt")
        clue_candidate = next(item for item in await list_candidates(db, project_id) if item.revision_id == clue_revision.id)
        adopted = await resolve_candidate(db, project_id, clue_candidate.id, "adopt")
        assert adopted.status == "adopted"
        assert adopted.proposed_value["materialized"]["type"] == "foreshadow"
