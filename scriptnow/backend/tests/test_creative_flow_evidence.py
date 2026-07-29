from pathlib import Path

import pytest

from scriptnow.diagnostics import creative_flow_evidence
from scriptnow.diagnostics.creative_flow_evidence import collect_persisted_evidence
from scriptnow.platform.creative_flow_audit import (
    ObservedArtifact,
    ObservedStage,
    audit_flow,
    load_scenario,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    RunStatus,
    TenantModel,
)

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


@pytest.mark.asyncio
async def test_completed_flow_uses_latest_successful_publication_not_later_failed_attempt(
    monkeypatch,
):
    scenario = load_scenario(GOLDEN_DIR / "novel-original.json")

    async def complete_novel_evidence(session, project):
        del session, project
        return (
            [
                ObservedStage(
                    id=stage.id,
                    status="succeeded",
                    artifacts=[
                        ObservedArtifact(
                            id=f"{stage.id}-artifact",
                            kind=stage.required_artifacts[0],
                            revision="v1",
                            readable=True,
                            persisted=True,
                            next_stage_consumable=True,
                        )
                    ],
                )
                for stage in scenario.stages
            ],
            [],
        )

    monkeypatch.setattr(
        creative_flow_evidence,
        "_novel_evidence",
        complete_novel_evidence,
    )
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            tenant = TenantModel(name="Evidence Studio")
            session.add(tenant)
            await session.flush()
            project = ProjectModel(
                tenant_id=tenant.id,
                name="Completed Novel",
                medium=ProjectMedium.NOVEL,
            )
            session.add(project)
            await session.flush()
            successful = ProjectRunModel(
                tenant_id=tenant.id,
                project_id=project.id,
                idempotency_key="completed-publication",
                status=RunStatus.SUCCEEDED,
            )
            later_failure = ProjectRunModel(
                tenant_id=tenant.id,
                project_id=project.id,
                idempotency_key="later-retry",
                status=RunStatus.FAILED,
            )
            session.add_all([successful, later_failure])
            await session.flush()

            observation = await collect_persisted_evidence(
                session,
                scenario=scenario,
                project_id=project.id,
            )
    finally:
        await database.dispose()

    assert observation.status == "succeeded"
    assert observation.operation_id == successful.id
