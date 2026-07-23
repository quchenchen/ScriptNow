import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from uuid import uuid4

from sqlalchemy import func, select

from scriptflow_v7.platform.audit import AuditService
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    ProjectModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)


class WorkspaceViolation(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredFile:
    id: str
    original_name: str
    media_type: str
    byte_size: int
    status: str


class LocalWorkspaceService:
    EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"

    def __init__(
        self,
        database: Database,
        root: Path,
        *,
        max_file_bytes: int = 10 * 1024 * 1024,
        max_project_bytes: int = 100 * 1024 * 1024,
        max_project_files: int = 100,
    ) -> None:
        self.database = database
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes
        self.max_project_bytes = max_project_bytes
        self.max_project_files = max_project_files
        self.audit = AuditService(database)

    async def upload(
        self,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        filename: str,
        content: bytes,
        correlation_id: str,
    ) -> StoredFile:
        clean_name = self._safe_original_name(filename)
        if not content or len(content) > self.max_file_bytes:
            raise WorkspaceViolation("file size is outside quota")
        media_type, extension = self._sniff(content)
        quarantined = self.EICAR_MARKER in content
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise WorkspaceViolation("project is outside tenant scope")
            count, used = (
                await session.execute(
                    select(
                        func.count(WorkspaceFileModel.id),
                        func.coalesce(func.sum(WorkspaceFileModel.byte_size), 0),
                    ).where(WorkspaceFileModel.project_id == project_id)
                )
            ).one()
            if count >= self.max_project_files or int(used) + len(content) > self.max_project_bytes:
                raise WorkspaceViolation("project upload quota exceeded")
            storage_name = f"{uuid4().hex}{extension}"
            status = WorkspaceFileStatus.QUARANTINED if quarantined else WorkspaceFileStatus.READY
            record = WorkspaceFileModel(
                tenant_id=tenant_id,
                project_id=project_id,
                original_name=clean_name,
                storage_name=storage_name,
                media_type=media_type,
                byte_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                status=status,
            )
            session.add(record)
            await session.flush()
            destination = self._storage_dir(tenant_id, project_id, quarantined) / storage_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(destination, content)
            view = StoredFile(record.id, clean_name, media_type, len(content), str(status))
        await self.audit.record(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="workspace.upload",
            resource_type="workspace_file",
            resource_id=view.id,
            outcome="quarantined" if quarantined else "succeeded",
            correlation_id=correlation_id,
            details={"media_type": media_type, "byte_size": len(content)},
        )
        return view

    async def resolve_ready_file(self, *, tenant_id: str, project_id: str, file_id: str) -> Path:
        async with self.database.session() as session:
            record = await session.get(WorkspaceFileModel, file_id)
            if (
                record is None
                or record.tenant_id != tenant_id
                or record.project_id != project_id
                or record.status != WorkspaceFileStatus.READY
            ):
                raise WorkspaceViolation("file is unavailable")
            path = (self._storage_dir(tenant_id, project_id, False) / record.storage_name).resolve()
            self._assert_beneath(path, self._storage_dir(tenant_id, project_id, False))
            if path.is_symlink() or not path.is_file():
                raise WorkspaceViolation("workspace file is invalid")
            return path

    async def list_files(self, *, tenant_id: str, project_id: str) -> list[StoredFile]:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise WorkspaceViolation("project is outside tenant scope")
            records = (
                await session.scalars(
                    select(WorkspaceFileModel)
                    .where(
                        WorkspaceFileModel.tenant_id == tenant_id,
                        WorkspaceFileModel.project_id == project_id,
                    )
                    .order_by(WorkspaceFileModel.created_at)
                )
            ).all()
            return [
                StoredFile(
                    item.id, item.original_name, item.media_type, item.byte_size, str(item.status)
                )
                for item in records
            ]

    async def delete_file(
        self, *, tenant_id: str, project_id: str, file_id: str, actor_id: str, correlation_id: str
    ) -> None:
        async with self.database.session() as session:
            record = await session.get(WorkspaceFileModel, file_id)
            if record is None or record.tenant_id != tenant_id or record.project_id != project_id:
                raise WorkspaceViolation("file is outside tenant scope")
            quarantined = record.status == WorkspaceFileStatus.QUARANTINED
            path = self._storage_dir(tenant_id, project_id, quarantined) / record.storage_name
            path.unlink(missing_ok=True)
            await session.delete(record)
        await self.audit.record(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="workspace.delete",
            resource_type="workspace_file",
            resource_id=file_id,
            outcome="succeeded",
            correlation_id=correlation_id,
        )

    def resolve_tool_path(self, *, tenant_id: str, project_id: str, relative_path: str) -> Path:
        if PurePath(relative_path).is_absolute() or ".." in PurePath(relative_path).parts:
            raise WorkspaceViolation("path escapes project workspace")
        base = self._storage_dir(tenant_id, project_id, False)
        candidate = (base / relative_path).resolve()
        self._assert_beneath(candidate, base)
        return candidate

    def _storage_dir(self, tenant_id: str, project_id: str, quarantined: bool) -> Path:
        category = "quarantine" if quarantined else "projects"
        return self.root / category / tenant_id / project_id

    @staticmethod
    def _safe_original_name(filename: str) -> str:
        if not filename or filename != Path(filename).name or filename in {".", ".."}:
            raise WorkspaceViolation("invalid filename")
        return filename[:255]

    @staticmethod
    def _sniff(content: bytes) -> tuple[str, str]:
        if content.startswith(b"%PDF-"):
            return "application/pdf", ".pdf"
        if content.startswith(b"PK"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    if "word/document.xml" in archive.namelist():
                        return (
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            ".docx",
                        )
            except zipfile.BadZipFile as error:
                raise WorkspaceViolation("invalid archive") from error
        if b"\x00" not in content:
            try:
                content.decode("utf-8")
                return "text/plain", ".txt"
            except UnicodeDecodeError:
                pass
        raise WorkspaceViolation("unsupported or disguised file type")

    @staticmethod
    def _assert_beneath(path: Path, base: Path) -> None:
        try:
            path.relative_to(base.resolve())
        except ValueError as error:
            raise WorkspaceViolation("path escapes project workspace") from error

    @staticmethod
    def _atomic_write(destination: Path, content: bytes) -> None:
        temporary = destination.with_suffix(destination.suffix + ".uploading")
        with temporary.open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(destination)
