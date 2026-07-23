import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from scriptflow_v7.platform.backup import BackupError, BackupService
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    ProjectEventModel,
    ProjectModel,
    ProjectSnapshotModel,
    TenantModel,
    TokenAccountModel,
)


def _seed_database(path: Path) -> dict[str, str | int]:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE project_versions (id TEXT PRIMARY KEY, content_hash TEXT NOT NULL);
        CREATE TABLE project_events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE token_accounts (tenant_id TEXT PRIMARY KEY, balance INTEGER NOT NULL);
        INSERT INTO project_versions VALUES ('v1', 'abc123');
        INSERT INTO project_events VALUES ('e1', '{"action":"created"}');
        INSERT INTO token_accounts VALUES ('tenant-1', 9980);
        """
    )
    connection.commit()
    connection.close()
    return {"content_hash": "abc123", "event": '{"action":"created"}', "balance": 9980}


def _read_evidence(path: Path) -> dict[str, str | int]:
    connection = sqlite3.connect(path)
    try:
        return {
            "content_hash": connection.execute(
                "SELECT content_hash FROM project_versions"
            ).fetchone()[0],
            "event": connection.execute("SELECT payload FROM project_events").fetchone()[0],
            "balance": connection.execute("SELECT balance FROM token_accounts").fetchone()[0],
        }
    finally:
        connection.close()


def test_backup_restore_preserves_database_workspace_hash_events_and_balance(tmp_path) -> None:
    database = tmp_path / "source.sqlite3"
    expected = _seed_database(database)
    workspace = tmp_path / "source-workspace"
    source = workspace / "projects" / "tenant-1" / "project-1" / "source.txt"
    source.parent.mkdir(parents=True)
    source.write_text("不可丢失的创作素材", encoding="utf-8")

    service = BackupService()
    backup = service.create(database_path=database, workspace_root=workspace)
    assert backup.sha256 == hashlib.sha256(backup.content).hexdigest()
    restored_database = tmp_path / "restored" / "scriptflow.sqlite3"
    restored_workspace = tmp_path / "restored-workspace"
    manifest = service.restore(
        content=backup.content,
        target_database_path=restored_database,
        target_workspace_root=restored_workspace,
    )

    assert _read_evidence(restored_database) == expected
    restored_source = restored_workspace / "projects" / "tenant-1" / "project-1" / "source.txt"
    assert restored_source.read_text(encoding="utf-8") == "不可丢失的创作素材"
    assert manifest["format"] == "scriptflow-v7-backup"


def test_restore_rejects_tampering_path_traversal_and_nonempty_targets(tmp_path) -> None:
    database = tmp_path / "source.sqlite3"
    _seed_database(database)
    service = BackupService()
    backup = service.create(database_path=database, workspace_root=tmp_path / "none")
    input_zip = zipfile.ZipFile(io.BytesIO(backup.content))
    manifest = json.loads(input_zip.read("manifest.json"))
    manifest["files"][0]["sha256"] = "0" * 64
    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("database.sqlite3", input_zip.read("database.sqlite3"))
    input_zip.close()
    with pytest.raises(BackupError, match="hash"):
        service.restore(
            content=tampered.getvalue(),
            target_database_path=tmp_path / "tampered.sqlite3",
            target_workspace_root=tmp_path / "tampered-workspace",
        )

    existing = tmp_path / "existing.sqlite3"
    existing.write_bytes(b"keep")
    with pytest.raises(BackupError, match="empty"):
        service.restore(
            content=backup.content,
            target_database_path=existing,
            target_workspace_root=tmp_path / "new-workspace",
        )


@pytest.mark.asyncio
async def test_real_v7_golden_project_restore_preserves_hash_event_and_balance(tmp_path) -> None:
    database_path = tmp_path / "golden.sqlite3"
    database = Database.create(f"sqlite+aiosqlite:///{database_path}")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Golden Studio", tier="pro")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id, name="Golden Script", medium="script", source_mode="original"
        )
        session.add(project)
        await session.flush()
        snapshot = ProjectSnapshotModel(
            tenant_id=tenant.id,
            project_id=project.id,
            medium="script",
            version=1,
            name="Golden v1",
            scope=["all"],
            word_count=1200,
            content_hash="a" * 64,
        )
        event = ProjectEventModel(
            tenant_id=tenant.id,
            project_id=project.id,
            stream_key=f"project:{project.id}",
            sequence=1,
            event_key="golden:created",
            event_type="system",
            correlation_id="golden",
            idempotency_key="golden:created",
            payload={"action": "golden.created"},
        )
        account = TokenAccountModel(
            tenant_id=tenant.id,
            tier="pro",
            period_key="2026-07",
            monthly_available=499_000,
            credits_available=2_000,
        )
        session.add_all([snapshot, event, account])
        await session.flush()
        snapshot_id, tenant_id = snapshot.id, tenant.id
    await database.dispose()
    workspace = tmp_path / "golden-workspace"
    memory = workspace / "Memory" / tenant_id / project.id / "writer" / "decision.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("保留创作决策", encoding="utf-8")
    backup = BackupService().create(database_path=database_path, workspace_root=workspace)
    restored_database = tmp_path / "restored" / "v7.sqlite3"
    restored_workspace = tmp_path / "restored-workspace"
    BackupService().restore(
        content=backup.content,
        target_database_path=restored_database,
        target_workspace_root=restored_workspace,
    )
    connection = sqlite3.connect(restored_database)
    try:
        assert connection.execute(
            "SELECT content_hash FROM project_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone() == ("a" * 64,)
        assert connection.execute(
            "SELECT payload FROM project_events WHERE event_key = 'golden:created'"
        ).fetchone() == ('{"action": "golden.created"}',)
        assert connection.execute(
            "SELECT monthly_available, credits_available FROM token_accounts WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone() == (499_000, 2_000)
    finally:
        connection.close()
    assert (
        restored_workspace / "Memory" / tenant_id / project.id / "writer" / "decision.md"
    ).read_text(encoding="utf-8") == "保留创作决策"
