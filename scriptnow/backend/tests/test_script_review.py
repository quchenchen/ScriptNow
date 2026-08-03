from decimal import Decimal

import pytest
from sqlalchemy import select

from scriptnow.platform.agent_runtime import AgentRuntimeResult
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    TenantModel,
)
from scriptnow.review.domain import ReviewFindingModel
from scriptnow.script.domain import (
    RevisionStatus,
    ScriptBlueprintAnchorModel,
    ScriptBlueprintModel,
    ScriptDocumentRevisionModel,
    ScriptStoryCoreCandidateModel,
)
from scriptnow.script.review import script_ai_review_scene


@pytest.mark.asyncio
async def test_script_ai_review_persists_real_findings(monkeypatch) -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio", tier="plus")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="审读验证",
            medium=ProjectMedium.SCRIPT,
            direction={"script_format": "chinese-short", "language": "zh-CN"},
        )
        session.add(project)
        await session.flush()
        core = ScriptStoryCoreCandidateModel(
            project_id=project.id,
            generation=1,
            ordinal=1,
            idempotency_key="core-1",
            title="退婚反转",
            concept="订婚宴取消并翻盘",
            angles=["欲望", "阻力"],
            details={"narrative_engine": ["翻盘"]},
            status="adopted",
        )
        session.add(core)
        await session.flush()
        blueprint = ScriptBlueprintModel(
            project_id=project.id,
            version=1,
            story_core_candidate_id=core.id,
            adopted=True,
        )
        session.add(blueprint)
        await session.flush()
        session.add(
            ScriptBlueprintAnchorModel(
                blueprint_id=blueprint.id,
                kind="event",
                anchor_key="event:inciting",
                name="订婚宴反转",
                payload={"description": "取消订婚宴"},
            )
        )
        session.add(
            ScriptDocumentRevisionModel(
                project_id=project.id,
                scene_id="scene-1-1",
                revision_number=1,
                status=RevisionStatus.ADOPTED,
                idempotency_key="rev-1",
                blocks=[
                    {"para_id": "s1", "type": "slugline", "text": "1-1-1 宴会厅 夜 内"},
                    {"para_id": "a1", "type": "action", "text": "▲顾念攥紧戒指盒。"},
                    {"para_id": "c1", "type": "character", "text": "宋司衡（冷声）"},
                    {"para_id": "d1", "type": "dialogue", "text": "取消。"},
                ],
            )
        )
        await session.flush()
        tenant_id, project_id = tenant.id, project.id

    class FakeRuntime:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, **kwargs) -> AgentRuntimeResult:
            self.calls += 1
            return AgentRuntimeResult(
                text=(
                    '{"summary":"一句话总评","findings":['
                    '{"domain":"character","severity":"blocker","element_id":"d1",'
                    '"excerpt":"取消。","diagnosis":"对白无潜台词，信息量过低",'
                    '"suggestion":"改为带试探性的反问","confidence":"high"},'
                    '{"domain":"arc","severity":"major","element_id":"a1",'
                    '"excerpt":"▲顾念攥紧戒指盒。","diagnosis":"动作未体现蓝图内在压力",'
                    '"suggestion":"增加泄露心理的动作","confidence":"mid"}]}'
                ),
                runtime="agentscope",
                model_key="deepseek-v4-pro",
                input_tokens=1000,
                output_tokens=500,
                input_price_per_million=Decimal("3"),
                output_price_per_million=Decimal("6"),
            )

    runtime = FakeRuntime()
    result = await script_ai_review_scene(
        database,
        runtime,
        tenant_id=tenant_id,
        project_id=project_id,
        scene_id="scene-1-1",
        run_id="run-review-1",
    )
    assert result.model_key == "deepseek-v4-pro"
    async with database.session() as session:
        findings = (await session.scalars(select(ReviewFindingModel))).all()
    assert len(findings) == 2
    assert {f.severity for f in findings} == {"blocker", "major"}
    assert any("潜台词" in f.diagnosis for f in findings)
    await database.dispose()
