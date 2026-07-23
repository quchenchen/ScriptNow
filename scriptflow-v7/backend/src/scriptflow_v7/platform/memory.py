import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    AgentStateModel,
    MemoryAuditModel,
    MemoryEntryModel,
    ProjectModel,
    new_id,
)


class MemoryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AgentRuntimeStatus:
    context_percent: int | None
    memory_count: int


class MemoryService:
    def __init__(self, database: Database, root: Path) -> None:
        self.database = database
        self.root = root.resolve()

    async def add(
        self, *, tenant_id: str, project_id: str, role_key: str, actor_id: str, content: str
    ) -> str:
        await self._assert_project(tenant_id, project_id)
        entry_id = new_id()
        relative = self._relative(tenant_id, project_id, role_key, entry_id)
        digest = self._hash(content)
        self._write(relative, content)
        try:
            async with self.database.session() as session:
                session.add(
                    MemoryEntryModel(
                        id=entry_id,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        role_key=role_key,
                        relative_path=str(relative),
                        content_hash=digest,
                    )
                )
                session.add(
                    MemoryAuditModel(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        memory_entry_id=entry_id,
                        actor_id=actor_id,
                        operation="create",
                        after_hash=digest,
                    )
                )
        except BaseException:
            self._absolute(relative).unlink(missing_ok=True)
            raise
        return entry_id

    async def correct(
        self, *, tenant_id: str, project_id: str, entry_id: str, actor_id: str, content: str
    ) -> None:
        await self.replace(
            tenant_id=tenant_id,
            project_id=project_id,
            entry_id=entry_id,
            actor_id=actor_id,
            content=content,
            operation="correct",
        )

    async def replace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        entry_id: str,
        actor_id: str,
        content: str,
        operation: str,
    ) -> None:
        if operation not in {"correct", "compress"}:
            raise MemoryError("unsupported memory operation")
        async with self.database.session() as session:
            entry = await session.get(MemoryEntryModel, entry_id)
            self._assert_entry(entry, tenant_id, project_id)
            assert entry is not None
            before = entry.content_hash
            after = self._hash(content)
            self._write(Path(entry.relative_path), content)
            entry.content_hash = after
            session.add(
                MemoryAuditModel(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    memory_entry_id=entry_id,
                    actor_id=actor_id,
                    operation=operation,
                    before_hash=before,
                    after_hash=after,
                )
            )

    async def read(self, *, tenant_id: str, project_id: str, entry_id: str) -> str:
        async with self.database.session() as session:
            entry = await session.get(MemoryEntryModel, entry_id)
            self._assert_entry(entry, tenant_id, project_id)
            assert entry is not None
            return self._absolute(Path(entry.relative_path)).read_text(encoding="utf-8")

    async def delete(
        self, *, tenant_id: str, project_id: str, entry_id: str, actor_id: str
    ) -> None:
        async with self.database.session() as session:
            entry = await session.get(MemoryEntryModel, entry_id)
            self._assert_entry(entry, tenant_id, project_id)
            assert entry is not None
            self._absolute(Path(entry.relative_path)).unlink(missing_ok=True)
            session.add(
                MemoryAuditModel(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    memory_entry_id=entry_id,
                    actor_id=actor_id,
                    operation="delete",
                    before_hash=entry.content_hash,
                )
            )
            await session.delete(entry)

    async def recover_index(self, *, tenant_id: str, project_id: str, role_key: str) -> int:
        await self._assert_project(tenant_id, project_id)
        directory = self._absolute(Path("Memory") / tenant_id / project_id / role_key)
        if not directory.exists():
            return 0
        recovered = 0
        async with self.database.session() as session:
            known = set(
                await session.scalars(
                    select(MemoryEntryModel.id).where(
                        MemoryEntryModel.tenant_id == tenant_id,
                        MemoryEntryModel.project_id == project_id,
                        MemoryEntryModel.role_key == role_key,
                    )
                )
            )
            for path in directory.glob("*.md"):
                if path.stem in known or not path.is_file():
                    continue
                content = path.read_text(encoding="utf-8")
                relative = path.relative_to(self.root)
                session.add(
                    MemoryEntryModel(
                        id=path.stem,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        role_key=role_key,
                        relative_path=str(relative),
                        content_hash=self._hash(content),
                    )
                )
                recovered += 1
        return recovered

    async def save_agent_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        role_key: str,
        serialized_state: dict[str, object],
        context_tokens: int | None,
        context_limit: int | None,
    ) -> None:
        await self._assert_project(tenant_id, project_id)
        async with self.database.session() as session:
            state = (
                await session.scalars(
                    select(AgentStateModel).where(
                        AgentStateModel.tenant_id == tenant_id,
                        AgentStateModel.project_id == project_id,
                        AgentStateModel.role_key == role_key,
                    )
                )
            ).one_or_none()
            if state is None:
                state = AgentStateModel(
                    tenant_id=tenant_id, project_id=project_id, role_key=role_key
                )
                session.add(state)
            else:
                state.state_version += 1
            state.serialized_state = serialized_state
            state.context_tokens = context_tokens
            state.context_limit = context_limit

    async def runtime_status(
        self, *, tenant_id: str, project_id: str, role_key: str
    ) -> AgentRuntimeStatus:
        async with self.database.session() as session:
            state = (
                await session.scalars(
                    select(AgentStateModel).where(
                        AgentStateModel.tenant_id == tenant_id,
                        AgentStateModel.project_id == project_id,
                        AgentStateModel.role_key == role_key,
                    )
                )
            ).one_or_none()
            count = int(
                await session.scalar(
                    select(func.count(MemoryEntryModel.id)).where(
                        MemoryEntryModel.tenant_id == tenant_id,
                        MemoryEntryModel.project_id == project_id,
                        MemoryEntryModel.role_key == role_key,
                    )
                )
                or 0
            )
            percent = None
            if state and state.context_tokens is not None and state.context_limit:
                percent = min(100, round(state.context_tokens * 100 / state.context_limit))
            return AgentRuntimeStatus(percent, count)

    async def _assert_project(self, tenant_id: str, project_id: str) -> None:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise MemoryError("project is outside tenant scope")

    @staticmethod
    def _assert_entry(entry: MemoryEntryModel | None, tenant_id: str, project_id: str) -> None:
        if entry is None or entry.tenant_id != tenant_id or entry.project_id != project_id:
            raise MemoryError("memory is outside tenant scope")

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _relative(tenant_id: str, project_id: str, role_key: str, entry_id: str) -> Path:
        if any(
            "/" in value or ".." in value for value in (tenant_id, project_id, role_key, entry_id)
        ):
            raise MemoryError("invalid memory scope")
        return Path("Memory") / tenant_id / project_id / role_key / f"{entry_id}.md"

    def _absolute(self, relative: Path) -> Path:
        absolute = (self.root / relative).resolve()
        try:
            absolute.relative_to(self.root)
        except ValueError as error:
            raise MemoryError("memory path escapes root") from error
        return absolute

    def _write(self, relative: Path, content: str) -> None:
        destination = self._absolute(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(destination)
