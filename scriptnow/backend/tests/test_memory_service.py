import pytest
from sqlalchemy import select

from scriptnow.platform.database import Database
from scriptnow.platform.memory import MemoryError, MemoryService
from scriptnow.platform.models import (
    MemoryAuditModel,
    MemoryEntryModel,
    ProjectMedium,
    ProjectModel,
    TenantModel,
)


@pytest.fixture
async def memory_data(tmp_path):
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Story", medium=ProjectMedium.SCRIPT)
        session.add(project)
        await session.flush()
    service = MemoryService(database, tmp_path / "workspace")
    yield service, database, tenant, other, project
    await database.dispose()


@pytest.mark.asyncio
async def test_memory_file_is_source_of_truth_with_correction_delete_audit(memory_data) -> None:
    memory, database, tenant, _, project = memory_data
    entry_id = await memory.add(
        tenant_id=tenant.id,
        project_id=project.id,
        role_key="writer",
        actor_id="user",
        content="Keep the ending ambiguous.",
    )
    await memory.correct(
        tenant_id=tenant.id,
        project_id=project.id,
        entry_id=entry_id,
        actor_id="user",
        content="Keep the ending hopeful.",
    )
    async with database.session() as session:
        entry = await session.get(MemoryEntryModel, entry_id)
        assert entry is not None
        path = memory.root / entry.relative_path
        assert path.read_text() == "Keep the ending hopeful."
    await memory.delete(
        tenant_id=tenant.id,
        project_id=project.id,
        entry_id=entry_id,
        actor_id="admin",
    )
    assert not path.exists()
    async with database.session() as session:
        audits = (
            await session.scalars(select(MemoryAuditModel).order_by(MemoryAuditModel.created_at))
        ).all()
        assert [audit.operation for audit in audits] == ["create", "correct", "delete"]
        audits[0].operation = "tampered"
        with pytest.raises(ValueError, match="append-only"):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_runtime_status_uses_real_state_and_memory_count(memory_data) -> None:
    memory, _, tenant, _, project = memory_data
    disconnected = await memory.runtime_status(
        tenant_id=tenant.id, project_id=project.id, role_key="reviewer"
    )
    assert disconnected.context_percent is None
    assert disconnected.memory_count == 0

    await memory.add(
        tenant_id=tenant.id,
        project_id=project.id,
        role_key="reviewer",
        actor_id="agent",
        content="Avoid deus ex machina.",
    )
    await memory.save_agent_state(
        tenant_id=tenant.id,
        project_id=project.id,
        role_key="reviewer",
        serialized_state={"reply_id": "r1"},
        context_tokens=750,
        context_limit=1000,
    )
    connected = await memory.runtime_status(
        tenant_id=tenant.id, project_id=project.id, role_key="reviewer"
    )
    assert connected.context_percent == 75
    assert connected.memory_count == 1


@pytest.mark.asyncio
async def test_memory_index_recovery_and_tenant_isolation(memory_data) -> None:
    memory, database, tenant, other, project = memory_data
    entry_id = await memory.add(
        tenant_id=tenant.id,
        project_id=project.id,
        role_key="writer",
        actor_id="agent",
        content="A recovered decision.",
    )
    async with database.session() as session:
        entry = await session.get(MemoryEntryModel, entry_id)
        assert entry is not None
        await session.delete(entry)
    assert (
        await memory.recover_index(tenant_id=tenant.id, project_id=project.id, role_key="writer")
        == 1
    )
    with pytest.raises(MemoryError, match="tenant scope"):
        await memory.correct(
            tenant_id=other.id,
            project_id=project.id,
            entry_id=entry_id,
            actor_id="attacker",
            content="poison",
        )
