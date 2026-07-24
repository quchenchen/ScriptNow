import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BackupResult:
    content: bytes
    sha256: str
    manifest: dict[str, object]


class BackupService:
    FORMAT_VERSION = 1
    MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024

    def create(self, *, database_path: Path, workspace_root: Path) -> BackupResult:
        source_database = database_path.resolve()
        source_workspace = workspace_root.resolve()
        if not source_database.is_file():
            raise BackupError("SQLite database does not exist")
        with tempfile.TemporaryDirectory(prefix="scriptnow-backup-") as temporary:
            consistent_database = Path(temporary) / "database.sqlite3"
            source = sqlite3.connect(f"file:{source_database}?mode=ro", uri=True)
            destination = sqlite3.connect(consistent_database)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            members: list[tuple[str, Path]] = [("database.sqlite3", consistent_database)]
            if source_workspace.is_dir():
                for path in sorted(source_workspace.rglob("*")):
                    if path.is_symlink():
                        raise BackupError("workspace backup refuses symbolic links")
                    if path.is_file():
                        relative = path.relative_to(source_workspace).as_posix()
                        members.append((f"workspace/{relative}", path))
            files = [
                {"path": name, "size": path.stat().st_size, "sha256": _file_hash(path)}
                for name, path in members
            ]
            manifest: dict[str, object] = {
                "format": "scriptnow-backup",
                "version": self.FORMAT_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "files": files,
            }
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                )
                for name, path in members:
                    archive.write(path, name)
            content = output.getvalue()
            return BackupResult(content, hashlib.sha256(content).hexdigest(), manifest)

    def restore(
        self,
        *,
        content: bytes,
        target_database_path: Path,
        target_workspace_root: Path,
    ) -> dict[str, object]:
        target_database = target_database_path.resolve()
        target_workspace = target_workspace_root.resolve()
        if target_database.exists() or target_workspace.exists():
            raise BackupError("restore targets must be empty")
        target_database.parent.mkdir(parents=True, exist_ok=True)
        target_workspace.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest = self._validate(archive)
            staging = Path(
                tempfile.mkdtemp(prefix="scriptnow-restore-", dir=target_database.parent)
            )
            try:
                staged_database = staging / "database.sqlite3"
                staged_workspace = staging / "workspace"
                staged_workspace.mkdir()
                for item in manifest["files"]:
                    member = str(item["path"])
                    destination = (
                        staged_database
                        if member == "database.sqlite3"
                        else staged_workspace / PurePosixPath(member).relative_to("workspace")
                    )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("xb") as output:
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fsync(output.fileno())
                _verify_sqlite(staged_database)
                staged_database.replace(target_database)
                try:
                    staged_workspace.replace(target_workspace)
                except Exception:
                    target_database.unlink(missing_ok=True)
                    raise
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return manifest

    def _validate(self, archive: zipfile.ZipFile) -> dict[str, object]:
        names = archive.namelist()
        if names.count("manifest.json") != 1:
            raise BackupError("backup manifest is missing or duplicated")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BackupError("backup manifest is invalid") from error
        if manifest.get("format") != "scriptnow-backup" or manifest.get("version") != 1:
            raise BackupError("backup format is unsupported")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise BackupError("backup file manifest is empty")
        declared = set()
        for item in files:
            if not isinstance(item, dict):
                raise BackupError("backup file entry is invalid")
            name = str(item.get("path", ""))
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or name in declared:
                raise BackupError("backup member path is unsafe")
            if name != "database.sqlite3" and (not path.parts or path.parts[0] != "workspace"):
                raise BackupError("backup member is outside the allowed roots")
            if name not in names or names.count(name) != 1:
                raise BackupError("backup member is missing or duplicated")
            info = archive.getinfo(name)
            if info.file_size > self.MAX_MEMBER_BYTES or info.file_size != int(
                item.get("size", -1)
            ):
                raise BackupError("backup member size does not match manifest")
            digest = hashlib.sha256(archive.read(name)).hexdigest()
            if digest != item.get("sha256"):
                raise BackupError("backup member hash does not match manifest")
            declared.add(name)
        if "database.sqlite3" not in declared or set(names) != declared | {"manifest.json"}:
            raise BackupError("backup contains undeclared members")
        return manifest


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sqlite(path: Path) -> None:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if result != ("ok",):
        raise BackupError("restored SQLite integrity check failed")
