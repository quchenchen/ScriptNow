import pytest
from sqlalchemy import select

from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.domain import NovelDocumentRevisionModel, NovelRevisionStatus
from scriptnow.novel.history import NovelHistoryConflict, NovelHistoryService
from scriptnow.novel.project import initialize_novel_project
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectMedium, ProjectModel, TenantModel
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import RevisionStatus, ScriptDocumentRevisionModel
from scriptnow.script.history import ScriptHistoryConflict, ScriptHistoryService
from scriptnow.script.project import initialize_script_project


@pytest.fixture
async def history_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="History Studio")
        session.add(tenant)
        await session.flush()
        script = ProjectModel(tenant_id=tenant.id, name="剧本", medium=ProjectMedium.SCRIPT)
        novel = ProjectModel(tenant_id=tenant.id, name="小说", medium=ProjectMedium.NOVEL)
        session.add_all([script, novel])
        await session.flush()
        await initialize_script_project(session, script)
        await initialize_novel_project(session, novel)
        script_revision = ScriptDocumentRevisionModel(
            project_id=script.id,
            scene_id="scene-1",
            revision_number=1,
            blocks=[
                ScriptBlock(para_id="p1", type="action", text="旧稿动作。").model_dump(mode="json")
            ],
            status=RevisionStatus.ADOPTED,
            idempotency_key="script-v1",
        )
        novel_revision = NovelDocumentRevisionModel(
            project_id=novel.id,
            chapter_id="chapter-1",
            revision_number=1,
            blocks=[
                NovelBlock(block_id="b1", type="prose", text="旧稿正文。").model_dump(mode="json")
            ],
            status=NovelRevisionStatus.ADOPTED,
            idempotency_key="novel-v1",
        )
        session.add_all([script_revision, novel_revision])
    yield database, tenant, script, novel
    await database.dispose()


async def _replace_script(database, project_id: str, text: str, number: int) -> None:
    async with database.session() as session:
        current = (
            await session.scalars(
                select(ScriptDocumentRevisionModel).where(
                    ScriptDocumentRevisionModel.project_id == project_id,
                    ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                )
            )
        ).one()
        current.status = RevisionStatus.SUPERSEDED
        session.add(
            ScriptDocumentRevisionModel(
                project_id=project_id,
                scene_id="scene-1",
                revision_number=number,
                base_revision_id=current.id,
                blocks=[
                    ScriptBlock(para_id=f"p{number}", type="action", text=text).model_dump(
                        mode="json"
                    )
                ],
                status=RevisionStatus.ADOPTED,
                idempotency_key=f"script-v{number}",
            )
        )


@pytest.mark.asyncio
async def test_script_snapshot_diff_rollback_is_idempotent_and_reversible(history_data) -> None:
    database, tenant, script, _ = history_data
    service = ScriptHistoryService(database)
    old = await service.create_snapshot(tenant_id=tenant.id, project_id=script.id, name="旧稿")
    await _replace_script(database, script.id, "新稿动作。", 2)
    new = await service.create_snapshot(tenant_id=tenant.id, project_id=script.id, name="新稿")
    preview = await service.diff(tenant_id=tenant.id, project_id=script.id, snapshot_id=old.id)
    assert preview["units"][0]["status"] == "changed"
    with pytest.raises(ScriptHistoryConflict, match="changed"):
        await service.rollback(
            tenant_id=tenant.id,
            project_id=script.id,
            snapshot_id=old.id,
            expected_current_hash="stale",
            idempotency_key="rollback-old-stale",
        )
    restored_old = await service.rollback(
        tenant_id=tenant.id,
        project_id=script.id,
        snapshot_id=old.id,
        expected_current_hash=preview["current_hash"],
        idempotency_key="rollback-old",
    )
    replay = await service.rollback(
        tenant_id=tenant.id,
        project_id=script.id,
        snapshot_id=old.id,
        expected_current_hash=preview["current_hash"],
        idempotency_key="rollback-old",
    )
    assert replay[0].id == restored_old[0].id
    back_to_new = await service.diff(tenant_id=tenant.id, project_id=script.id, snapshot_id=new.id)
    restored_new = await service.rollback(
        tenant_id=tenant.id,
        project_id=script.id,
        snapshot_id=new.id,
        expected_current_hash=back_to_new["current_hash"],
        idempotency_key="rollback-new",
    )
    assert restored_old[0].revision_number == 3
    assert restored_new[0].revision_number == 4
    assert restored_new[0].blocks[0]["text"] == "新稿动作。"


@pytest.mark.asyncio
async def test_novel_snapshot_uses_block_contract_and_hash_conflict_guard(history_data) -> None:
    database, tenant, _, novel = history_data
    service = NovelHistoryService(database)
    snapshot = await service.create_snapshot(tenant_id=tenant.id, project_id=novel.id, name="初稿")
    async with database.session() as session:
        current = (
            await session.scalars(
                select(NovelDocumentRevisionModel).where(
                    NovelDocumentRevisionModel.project_id == novel.id,
                    NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                )
            )
        ).one()
        current.status = NovelRevisionStatus.SUPERSEDED
        session.add(
            NovelDocumentRevisionModel(
                project_id=novel.id,
                chapter_id="chapter-1",
                revision_number=2,
                base_revision_id=current.id,
                blocks=[
                    NovelBlock(block_id="b2", type="prose", text="新稿正文。").model_dump(
                        mode="json"
                    )
                ],
                status=NovelRevisionStatus.ADOPTED,
                idempotency_key="novel-v2",
            )
        )
    preview = await service.diff(tenant_id=tenant.id, project_id=novel.id, snapshot_id=snapshot.id)
    with pytest.raises(NovelHistoryConflict, match="changed"):
        await service.rollback(
            tenant_id=tenant.id,
            project_id=novel.id,
            snapshot_id=snapshot.id,
            expected_current_hash="stale",
            idempotency_key="novel-stale",
        )
    restored = await service.rollback(
        tenant_id=tenant.id,
        project_id=novel.id,
        snapshot_id=snapshot.id,
        expected_current_hash=preview["current_hash"],
        idempotency_key="novel-rollback",
    )
    assert restored[0].revision_number == 3
    assert restored[0].blocks[0]["text"] == "旧稿正文。"
