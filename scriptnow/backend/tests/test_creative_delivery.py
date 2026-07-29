import hashlib

import pytest
from sqlalchemy import select

from scriptnow.platform.creative_delivery import CreativeDeliveryService
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    CreativeDeliveryArtifactModel,
    ProjectMedium,
    ProjectModel,
    TenantModel,
)


@pytest.mark.asyncio
async def test_delivery_artifact_is_idempotent_versioned_and_verifiable():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            tenant = TenantModel(name="Delivery Studio")
            session.add(tenant)
            await session.flush()
            project = ProjectModel(
                tenant_id=tenant.id,
                name="Delivered Work",
                medium=ProjectMedium.NOVEL,
            )
            session.add(project)
            await session.flush()

        service = CreativeDeliveryService(database)
        artifact = b"durable export"
        first = await service.record(
            tenant_id=tenant.id,
            project_id=project.id,
            domain="translation",
            stage="export",
            kind="translation_docx",
            idempotency_key="request-1",
            payload={"chapter_count": 1},
            artifact=artifact,
        )
        repeated = await service.record(
            tenant_id=tenant.id,
            project_id=project.id,
            domain="translation",
            stage="export",
            kind="translation_docx",
            idempotency_key="request-1",
            payload={"chapter_count": 99},
            artifact=b"must not replace the first artifact",
        )
        second = await service.record(
            tenant_id=tenant.id,
            project_id=project.id,
            domain="translation",
            stage="export",
            kind="translation_docx",
            idempotency_key="request-2",
            payload={"chapter_count": 2},
            artifact=b"second export",
        )

        async with database.session() as session:
            rows = list(
                await session.scalars(
                    select(CreativeDeliveryArtifactModel)
                    .where(CreativeDeliveryArtifactModel.project_id == project.id)
                    .order_by(CreativeDeliveryArtifactModel.version)
                )
            )
    finally:
        await database.dispose()

    assert repeated.id == first.id
    assert first.version == 1
    assert second.version == 2
    assert len(rows) == 2
    assert rows[0].payload == {"chapter_count": 1}
    assert rows[0].artifact == artifact
    assert rows[0].artifact_sha256 == hashlib.sha256(artifact).hexdigest()
    assert rows[0].byte_size == len(artifact)
