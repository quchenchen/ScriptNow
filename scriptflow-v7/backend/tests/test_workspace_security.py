import io
import zipfile

import pytest
from sqlalchemy import select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import AuditLogModel, ProjectMedium, ProjectModel, TenantModel
from scriptflow_v7.platform.workspace import LocalWorkspaceService, WorkspaceViolation


def docx_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", "<document>story</document>")
    return output.getvalue()


@pytest.fixture
async def workspace_data(tmp_path):
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(tenant_id=tenant.id, name="Story", medium=ProjectMedium.NOVEL)
        session.add(project)
        await session.flush()
    service = LocalWorkspaceService(
        database,
        tmp_path / "workspace",
        max_file_bytes=1024,
        max_project_bytes=2048,
        max_project_files=2,
    )
    yield service, database, tenant, other, project
    await database.dispose()


@pytest.mark.asyncio
async def test_upload_sniffs_content_stores_random_name_and_audits(workspace_data) -> None:
    workspace, database, tenant, _, project = workspace_data
    uploaded_bytes = docx_bytes()
    stored = await workspace.upload(
        tenant_id=tenant.id,
        project_id=project.id,
        actor_id="user-1",
        filename="draft.exe",
        content=uploaded_bytes,
        correlation_id="trace-1",
    )
    path = await workspace.resolve_ready_file(
        tenant_id=tenant.id, project_id=project.id, file_id=stored.id
    )

    assert stored.media_type.endswith("wordprocessingml.document")
    assert path.suffix == ".docx"
    assert path.name != "draft.exe"
    assert path.read_bytes() == uploaded_bytes
    async with database.session() as session:
        audit = (await session.scalars(select(AuditLogModel))).one()
        assert audit.action == "workspace.upload"
        assert audit.details["media_type"] == stored.media_type
        audit.outcome = "tampered"
        with pytest.raises(ValueError, match="append-only"):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_path_traversal_cross_tenant_and_disguised_content_are_rejected(
    workspace_data,
) -> None:
    workspace, _, tenant, other, project = workspace_data
    for path in ["../secret", "/etc/passwd", "folder/../../secret"]:
        with pytest.raises(WorkspaceViolation, match="escapes"):
            workspace.resolve_tool_path(
                tenant_id=tenant.id, project_id=project.id, relative_path=path
            )
    with pytest.raises(WorkspaceViolation, match="filename"):
        await workspace.upload(
            tenant_id=tenant.id,
            project_id=project.id,
            actor_id="user",
            filename="../attack.txt",
            content=b"text",
            correlation_id="trace",
        )
    with pytest.raises(WorkspaceViolation, match="tenant scope"):
        await workspace.upload(
            tenant_id=other.id,
            project_id=project.id,
            actor_id="attacker",
            filename="attack.txt",
            content=b"text",
            correlation_id="trace",
        )
    with pytest.raises(WorkspaceViolation, match="disguised"):
        await workspace.upload(
            tenant_id=tenant.id,
            project_id=project.id,
            actor_id="user",
            filename="fake.pdf",
            content=b"\x00\x01binary",
            correlation_id="trace",
        )


@pytest.mark.asyncio
async def test_malware_marker_is_quarantined_and_quota_is_enforced(workspace_data) -> None:
    workspace, _, tenant, _, project = workspace_data
    quarantined = await workspace.upload(
        tenant_id=tenant.id,
        project_id=project.id,
        actor_id="user",
        filename="eicar.txt",
        content=b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
        correlation_id="trace",
    )
    assert quarantined.status == "quarantined"
    with pytest.raises(WorkspaceViolation, match="unavailable"):
        await workspace.resolve_ready_file(
            tenant_id=tenant.id, project_id=project.id, file_id=quarantined.id
        )
    await workspace.upload(
        tenant_id=tenant.id,
        project_id=project.id,
        actor_id="user",
        filename="one.txt",
        content=b"one",
        correlation_id="trace",
    )
    with pytest.raises(WorkspaceViolation, match="quota"):
        await workspace.upload(
            tenant_id=tenant.id,
            project_id=project.id,
            actor_id="user",
            filename="two.txt",
            content=b"two",
            correlation_id="trace",
        )
    with pytest.raises(WorkspaceViolation, match="file size"):
        await workspace.upload(
            tenant_id=tenant.id,
            project_id=project.id,
            actor_id="user",
            filename="huge.txt",
            content=b"x" * 1025,
            correlation_id="trace",
        )
