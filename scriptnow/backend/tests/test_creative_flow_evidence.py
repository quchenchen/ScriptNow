from pathlib import Path

import pytest

from scriptnow.diagnostics.creative_flow_evidence import collect_persisted_evidence
from scriptnow.platform.creative_flow_audit import audit_flow, load_scenario
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectMedium, ProjectModel, TenantModel

GOLDEN_DIR = Path(__file__).parents[1] / "golden" / "creative-flow-v1"


@pytest.mark.asyncio
async def test_collector_marks_unmaterialized_flow_as_partial_without_fabricating_events():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            tenant = TenantModel(name="Evidence Studio")
            session.add(tenant)
            await session.flush()
            project = ProjectModel(
                tenant_id=tenant.id,
                name="Unmaterialized Novel",
                medium=ProjectMedium.NOVEL,
            )
            session.add(project)
            await session.flush()
            observation = await collect_persisted_evidence(
                session,
                scenario=load_scenario(GOLDEN_DIR / "novel-original.json"),
                project_id=project.id,
            )
    finally:
        await database.dispose()

    assert observation.status == "partial"
    assert observation.operation_id == f"untracked-project:{project.id}"
    assert all(stage.status == "partial" for stage in observation.stages)
    assert observation.decisions == []
    report = audit_flow(
        load_scenario(GOLDEN_DIR / "novel-original.json"),
        observation,
    )
    assert report.passed is False
    assert any(item.code == "missing_consumable_artifact" for item in report.findings)


@pytest.mark.asyncio
async def test_collector_rejects_project_from_another_domain():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            tenant = TenantModel(name="Evidence Studio")
            session.add(tenant)
            await session.flush()
            project = ProjectModel(
                tenant_id=tenant.id,
                name="Script",
                medium=ProjectMedium.SCRIPT,
            )
            session.add(project)
            await session.flush()
            with pytest.raises(ValueError, match="medium"):
                await collect_persisted_evidence(
                    session,
                    scenario=load_scenario(GOLDEN_DIR / "novel-original.json"),
                    project_id=project.id,
                )
    finally:
        await database.dispose()
