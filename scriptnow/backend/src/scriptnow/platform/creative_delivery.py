import hashlib

from sqlalchemy import func, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import CreativeDeliveryArtifactModel, DeliveryStatus


class CreativeDeliveryService:
    """Persist transport-neutral evidence without owning domain payload semantics."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def record(
        self,
        *,
        tenant_id: str,
        project_id: str,
        domain: str,
        stage: str,
        kind: str,
        idempotency_key: str,
        payload: dict[str, object],
        artifact: bytes | None = None,
    ) -> CreativeDeliveryArtifactModel:
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(CreativeDeliveryArtifactModel).where(
                        CreativeDeliveryArtifactModel.project_id == project_id,
                        CreativeDeliveryArtifactModel.domain == domain,
                        CreativeDeliveryArtifactModel.stage == stage,
                        CreativeDeliveryArtifactModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return existing
            version = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(
                                func.max(CreativeDeliveryArtifactModel.version), 0
                            )
                        ).where(
                            CreativeDeliveryArtifactModel.project_id == project_id,
                            CreativeDeliveryArtifactModel.domain == domain,
                            CreativeDeliveryArtifactModel.stage == stage,
                        )
                    )
                    or 0
                )
                + 1
            )
            item = CreativeDeliveryArtifactModel(
                tenant_id=tenant_id,
                project_id=project_id,
                domain=domain,
                stage=stage,
                kind=kind,
                version=version,
                idempotency_key=idempotency_key,
                status=DeliveryStatus.SUCCEEDED,
                payload=payload,
                artifact=artifact,
                artifact_sha256=hashlib.sha256(artifact).hexdigest() if artifact else None,
                byte_size=len(artifact) if artifact else None,
            )
            session.add(item)
            await session.flush()
            return item
