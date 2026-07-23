import json

import pytest
from pydantic import ValidationError

from scriptflow_v7.novel.domain import NovelDocumentRevisionModel
from scriptflow_v7.novel.project import NovelStoryMapModel
from scriptflow_v7.novel.quality import (
    NOVEL_QUALITY_RUBRIC_VERSION,
    NovelQualityAssessment,
    NovelQualityDimension,
    NovelQualityDraft,
    NovelQualityError,
    NovelQualityReadiness,
    NovelQualityService,
    NovelQualityVerdict,
)
from scriptflow_v7.novel.quality_evaluator import NovelQualityEvaluator
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import ProjectMedium, ProjectModel, TenantModel


def quality_draft(
    *,
    revise: NovelQualityDimension | None = None,
    block: NovelQualityDimension | None = None,
) -> NovelQualityDraft:
    assessments = []
    for dimension in NovelQualityDimension:
        verdict = NovelQualityVerdict.PASS
        score = 5
        if dimension == revise:
            verdict, score = NovelQualityVerdict.REVISE, 3
        if dimension == block:
            verdict, score = NovelQualityVerdict.BLOCK, 1
        assessments.append(
            NovelQualityAssessment(
                dimension=dimension,
                verdict=verdict,
                score=score,
                evidence=(f"Textual evidence for {dimension.value}.",),
                diagnosis=f"Assessment for {dimension.value}.",
                repair=f"Repair action for {dimension.value}.",
            )
        )
    return NovelQualityDraft(dimensions=tuple(assessments), summary="Chapter maturity review.")


@pytest.fixture
async def quality_data():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Novel quality")
        other = TenantModel(name="Other")
        session.add_all([tenant, other])
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Moonbound",
            medium=ProjectMedium.NOVEL,
            direction={"language": "en-US"},
        )
        session.add(project)
        await session.flush()
        session.add(
            NovelStoryMapModel(
                project_id=project.id,
                volumes=[
                    {
                        "id": "volume-1",
                        "chapters": [
                            {"id": "chapter-0", "title": "Before"},
                            {"id": "chapter-1", "title": "Now"},
                        ],
                    }
                ],
            )
        )
        session.add_all(
            [
                NovelDocumentRevisionModel(
                    project_id=project.id,
                    chapter_id="chapter-0",
                    revision_number=1,
                    source="agent",
                    blocks=[{"block_id": "old", "type": "prose", "text": "Old continuity."}],
                    status="superseded",
                    idempotency_key="chapter-0-v1",
                ),
                NovelDocumentRevisionModel(
                    project_id=project.id,
                    chapter_id="chapter-0",
                    revision_number=2,
                    source="human",
                    blocks=[{"block_id": "new", "type": "prose", "text": "Human continuity."}],
                    status="candidate",
                    idempotency_key="chapter-0-v2",
                ),
            ]
        )
        revision = NovelDocumentRevisionModel(
            project_id=project.id,
            chapter_id="chapter-1",
            revision_number=1,
            blocks=[{"block_id": "p1", "type": "prose", "text": "A consequential choice."}],
            status="candidate",
            idempotency_key="chapter-1-v1",
        )
        session.add(revision)
        await session.flush()
    yield NovelQualityService(database), tenant, other, project, revision
    await database.dispose()


def test_quality_draft_requires_every_dimension_once():
    draft = quality_draft()
    with pytest.raises(ValidationError, match="every Novel quality dimension"):
        NovelQualityDraft(dimensions=draft.dimensions[:-1], summary="Incomplete review")


def test_quality_readiness_uses_blockers_and_revision_axes():
    assert quality_draft().readiness == NovelQualityReadiness.READY
    assert (
        quality_draft(revise=NovelQualityDimension.NARRATIVE_VOICE).readiness
        == NovelQualityReadiness.REVISION_REQUIRED
    )
    assert (
        quality_draft(block=NovelQualityDimension.SOURCE_BOUNDARY).readiness
        == NovelQualityReadiness.BLOCKED
    )


def test_quality_evaluator_parses_fenced_strict_report():
    draft = quality_draft()
    parsed = NovelQualityEvaluator.parse(
        f"```json\n{draft.model_dump_json()}\n```"
    )
    assert parsed == draft


def test_quality_evaluator_rejects_incomplete_report():
    with pytest.raises(NovelQualityError, match="质量报告不完整"):
        NovelQualityEvaluator.parse(
            '{"dimensions":[{"dimension":"narrative_voice","verdict":"pass",'
            '"score":5,"evidence":["A line."],"diagnosis":"Strong voice.",'
            '"repair":"Preserve it."}],"summary":"Incomplete."}'
        )


def test_quality_evaluator_normalizes_provider_extras_without_losing_assessment():
    raw = quality_draft().model_dump(mode="json")
    raw["revision_candidate"] = {"blocks": ["must not enter report storage"]}
    raw["dimensions"][0]["commentary"] = "extra provider explanation"
    raw["dimensions"][0]["recommendation"] = raw["dimensions"][0].pop("repair")

    parsed = NovelQualityEvaluator.parse(json.dumps(raw))

    assert parsed == quality_draft()


def test_quality_repair_prompt_requests_complete_contract_without_rereview():
    prompt = NovelQualityEvaluator._repair_prompt('{"partial":true}')

    assert "Do not re-review" in prompt
    assert "character_agency" in prompt
    assert '{"partial":true}' in prompt


async def test_quality_report_is_version_bound_and_idempotent(quality_data):
    service, tenant, _, project, revision = quality_data
    report = await service.record(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        revision_id=revision.id,
        draft=quality_draft(revise=NovelQualityDimension.PROSE_TEXTURE),
        skill_plan_fingerprint="skill-plan-sha256",
        source_profile_version="source-profile-v2",
        author="novel-reviewer",
        idempotency_key="quality-1",
    )
    duplicate = await service.record(
        tenant_id=tenant.id,
        project_id=project.id,
        chapter_id="chapter-1",
        revision_id=revision.id,
        draft=quality_draft(),
        skill_plan_fingerprint="different-plan",
        source_profile_version=None,
        author="other-reviewer",
        idempotency_key="quality-1",
    )
    assert duplicate.id == report.id
    assert report.rubric_version == NOVEL_QUALITY_RUBRIC_VERSION
    assert report.revision_id == revision.id
    assert report.overall_status == NovelQualityReadiness.REVISION_REQUIRED
    assert report.maturity_score == 95
    assert report.skill_plan_fingerprint == "skill-plan-sha256"
    history = await service.history(
        tenant_id=tenant.id, project_id=project.id, chapter_id="chapter-1"
    )
    assert [item.id for item in history] == [report.id]


async def test_quality_report_rejects_cross_tenant_and_wrong_chapter(quality_data):
    service, tenant, other, project, revision = quality_data
    kwargs = {
        "project_id": project.id,
        "chapter_id": "chapter-1",
        "revision_id": revision.id,
        "draft": quality_draft(),
        "skill_plan_fingerprint": "skill-plan",
        "source_profile_version": None,
        "author": "reviewer",
        "idempotency_key": "quality-boundary",
    }
    with pytest.raises(NovelQualityError, match="tenant"):
        await service.record(tenant_id=other.id, **kwargs)
    with pytest.raises(NovelQualityError, match="chapter"):
        await service.record(tenant_id=tenant.id, **{**kwargs, "chapter_id": "chapter-2"})


async def test_development_evaluator_records_review_without_adopting_candidate(quality_data):
    service, tenant, _, project, revision = quality_data
    evaluator = NovelQualityEvaluator(service.database, Settings())

    class MockOnlyRuntime:
        async def status(self, **kwargs):
            del kwargs
            return {"roles": {"reviewer": {"connected": False, "reason": "mock_only"}}}

    evaluator.runtime = MockOnlyRuntime()  # type: ignore[assignment]
    report = await evaluator.evaluate(
        tenant_id=tenant.id,
        project=project,
        chapter_id="chapter-1",
        revision_id=revision.id,
        idempotency_key="development-quality",
    )
    assert report.overall_status == NovelQualityReadiness.REVISION_REQUIRED
    assert report.revision_id == revision.id
    assert revision.status == "candidate"


async def test_quality_context_uses_latest_effective_human_continuity(quality_data):
    service, tenant, _, project, revision = quality_data
    evaluator = NovelQualityEvaluator(service.database, Settings())
    context = await evaluator._context(
        tenant_id=tenant.id,
        project=project,
        chapter_id="chapter-1",
        revision_id=revision.id,
    )
    prior = context["prior_chapter_revisions"]
    assert len(prior) == 1
    assert prior[0]["source"] == "human"
    assert prior[0]["blocks"][0]["text"] == "Human continuity."
