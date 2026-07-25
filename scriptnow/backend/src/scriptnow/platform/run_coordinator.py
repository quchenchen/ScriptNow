from dataclasses import dataclass

from sqlalchemy import select

from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, ProjectRunModel, RunStatus


class RunTransitionError(RuntimeError):
    pass


TERMINAL = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
TRANSITIONS: dict[str, set[str]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {
        RunStatus.WAITING,
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.WAITING: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED},
}


@dataclass(frozen=True, slots=True)
class RunView:
    id: str
    tenant_id: str
    project_id: str
    status: str
    state_version: int
    waiting_reason: str | None
    error_code: str | None


class RunCoordinator:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def enqueue(self, *, tenant_id: str, project_id: str, idempotency_key: str) -> RunView:
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(ProjectRunModel).where(
                        ProjectRunModel.tenant_id == tenant_id,
                        ProjectRunModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                if existing.project_id != project_id:
                    raise RunTransitionError("idempotency key belongs to another project")
                return self._view(existing)
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise RunTransitionError("project is outside tenant scope")
            run = ProjectRunModel(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
            )
            session.add(run)
            await session.flush()
            return self._view(run)

    async def transition(
        self,
        *,
        tenant_id: str,
        run_id: str,
        target: RunStatus,
        waiting_reason: str | None = None,
        error_code: str | None = None,
    ) -> RunView:
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                raise RunTransitionError("run is outside tenant scope")
            if target not in TRANSITIONS.get(run.status, set()):
                raise RunTransitionError(f"invalid run transition: {run.status} -> {target}")
            if target == RunStatus.WAITING and not waiting_reason:
                raise RunTransitionError("waiting transition requires a reason")
            if target == RunStatus.FAILED and not error_code:
                raise RunTransitionError("failed transition requires an error code")
            run.status = target
            run.waiting_reason = waiting_reason if target == RunStatus.WAITING else None
            run.error_code = error_code if target == RunStatus.FAILED else None
            run.state_version += 1
            await session.flush()
            return self._view(run)

    async def recoverable(self) -> list[RunView]:
        async with self.database.session() as session:
            runs = (
                await session.scalars(
                    select(ProjectRunModel)
                    .where(
                        ProjectRunModel.status.in_(
                            [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING]
                        )
                    )
                    .order_by(ProjectRunModel.created_at)
                )
            ).all()
            return [self._view(run) for run in runs]

    @staticmethod
    def _view(run: ProjectRunModel) -> RunView:
        return RunView(
            id=run.id,
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            status=str(run.status),
            state_version=run.state_version,
            waiting_reason=run.waiting_reason,
            error_code=run.error_code,
        )

    async def status(self, *, tenant_id: str, run_id: str) -> RunView | None:
        """Return current run status or None if not found."""
        async with self.database.session() as session:
            run = await session.get(ProjectRunModel, run_id)
            if run is None or run.tenant_id != tenant_id:
                return None
            return self._view(run)
