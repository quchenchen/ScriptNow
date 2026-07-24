from dataclasses import dataclass

from sqlalchemy import func, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreditLedgerModel,
    ProjectModel,
    ProjectRunModel,
    RuntimeConfigSnapshotModel,
    TokenUsageModel,
    UsageReservationModel,
)


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    orphan_runtime_snapshots: int
    cross_tenant_runs: int
    cross_tenant_usage: int
    duplicate_usage_events: int
    duplicate_ledger_operations: int

    @property
    def ok(self) -> bool:
        return not any(
            (
                self.orphan_runtime_snapshots,
                self.cross_tenant_runs,
                self.cross_tenant_usage,
                self.duplicate_usage_events,
                self.duplicate_ledger_operations,
            )
        )


class IntegrityAuditor:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def audit(self) -> IntegrityReport:
        async with self.database.session() as session:
            orphan_snapshots = int(
                await session.scalar(
                    select(func.count())
                    .select_from(RuntimeConfigSnapshotModel)
                    .outerjoin(
                        ProjectRunModel, ProjectRunModel.id == RuntimeConfigSnapshotModel.run_id
                    )
                    .where(ProjectRunModel.id.is_(None))
                )
                or 0
            )
            cross_runs = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProjectRunModel)
                    .join(ProjectModel, ProjectModel.id == ProjectRunModel.project_id)
                    .where(ProjectRunModel.tenant_id != ProjectModel.tenant_id)
                )
                or 0
            )
            cross_usage = int(
                await session.scalar(
                    select(func.count())
                    .select_from(TokenUsageModel)
                    .join(ProjectRunModel, ProjectRunModel.id == TokenUsageModel.run_id)
                    .join(ProjectModel, ProjectModel.id == TokenUsageModel.project_id)
                    .join(
                        UsageReservationModel,
                        UsageReservationModel.id == TokenUsageModel.reservation_id,
                    )
                    .where(
                        (TokenUsageModel.tenant_id != ProjectRunModel.tenant_id)
                        | (TokenUsageModel.tenant_id != ProjectModel.tenant_id)
                        | (TokenUsageModel.tenant_id != UsageReservationModel.tenant_id)
                    )
                )
                or 0
            )
            usage_groups = (
                select(TokenUsageModel.run_id, TokenUsageModel.framework_event_id)
                .group_by(TokenUsageModel.run_id, TokenUsageModel.framework_event_id)
                .having(func.count() > 1)
                .subquery()
            )
            duplicate_usage = int(
                await session.scalar(select(func.count()).select_from(usage_groups)) or 0
            )
            ledger_groups = (
                select(CreditLedgerModel.reservation_id, CreditLedgerModel.operation)
                .where(CreditLedgerModel.reservation_id.is_not(None))
                .group_by(CreditLedgerModel.reservation_id, CreditLedgerModel.operation)
                .having(func.count() > 1)
                .subquery()
            )
            duplicate_ledger = int(
                await session.scalar(select(func.count()).select_from(ledger_groups)) or 0
            )
        return IntegrityReport(
            orphan_snapshots, cross_runs, cross_usage, duplicate_usage, duplicate_ledger
        )
