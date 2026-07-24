from dataclasses import dataclass

from sqlalchemy import select

from scriptnow.platform.database import Database
from scriptnow.platform.models import AuditLogModel


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    action: str
    resource_id: str
    outcome: str
    details: dict[str, object]


class AuditService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def record(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        correlation_id: str,
        details: dict[str, object] | None = None,
    ) -> AuditEvent:
        async with self.database.session() as session:
            record = AuditLogModel(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                correlation_id=correlation_id,
                details=details or {},
            )
            session.add(record)
            await session.flush()
            return self._view(record)

    async def for_tenant(self, tenant_id: str) -> list[AuditEvent]:
        async with self.database.session() as session:
            records = (
                await session.scalars(
                    select(AuditLogModel)
                    .where(AuditLogModel.tenant_id == tenant_id)
                    .order_by(AuditLogModel.created_at)
                )
            ).all()
            return [self._view(record) for record in records]

    @staticmethod
    def _view(record: AuditLogModel) -> AuditEvent:
        return AuditEvent(
            record.id, record.action, record.resource_id, record.outcome, dict(record.details)
        )
