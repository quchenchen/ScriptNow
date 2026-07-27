import json
import re
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import ValidationError
from sqlalchemy import select

from scriptnow.novel.continuity import latest_effective_revisions
from scriptnow.novel.domain import (
    NovelBlueprintAnchorModel,
    NovelBlueprintModel,
    NovelDocumentRevisionModel,
    NovelQualityReportModel,
)
from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.novel.quality import (
    NovelQualityAssessment,
    NovelQualityDimension,
    NovelQualityDraft,
    NovelQualityError,
    NovelQualityService,
    NovelQualityVerdict,
)
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    DistillationDecision,
    ProjectModel,
    RunStatus,
    SourceProfileModel,
)
from scriptnow.platform.run_coordinator import RunCoordinator


class NovelQualityEvaluator:
    """Execute the Novel reviewer against one immutable candidate revision."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.reports = NovelQualityService(database)

    async def evaluate(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        chapter_id: str,
        revision_id: str,
        idempotency_key: str,
    ) -> NovelQualityReportModel:
        context = await self._context(
            tenant_id=tenant_id,
            project=project,
            chapter_id=chapter_id,
            revision_id=revision_id,
        )
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project.id)
        reviewer = dict(dict(status["roles"])["reviewer"])
        run_id: str | None = None
        if self.settings.environment != "production" and reviewer.get("reason") == "mock_only":
            draft = self._test_draft(context)
            fingerprint = "development-mock-quality-v1"
        else:
            if not reviewer.get("connected"):
                raise NovelQualityError(
                    f"real reviewer runtime is unavailable: {reviewer.get('reason') or 'unknown'}"
                )
            run = await self.runs.enqueue(
                tenant_id=tenant_id,
                project_id=project.id,
                idempotency_key=f"novel-quality:{chapter_id}:{revision_id}:{idempotency_key}",
            )
            run_id = run.id
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING
            )
            try:
                result = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    role="reviewer",
                    content=self._prompt(context),
                    context_snapshot=context,
                    stage_override="review",
                    explicit_skill_keys=("novel-review", "novel-serial-quality-review"),
                )
                try:
                    draft = self.parse(result.text)
                except NovelQualityError:
                    repaired = await self.runtime.generate(
                        tenant_id=tenant_id,
                        run_id=run.id,
                        role="reviewer",
                        content=self._repair_prompt(result.text),
                        context_snapshot={
                            "project_id": project.id,
                            "chapter_id": chapter_id,
                            "revision_id": revision_id,
                            "task": "quality-report-contract-repair",
                        },
                        stage_override="review",
                        explicit_skill_keys=("novel-review",),
                    )
                    draft = self.parse(repaired.text)
                fingerprint = result.config_fingerprint
            except (AgentRuntimeError, NovelQualityError, ValidationError, ValueError) as error:
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="novel_quality_failed",
                )
                raise NovelQualityError(str(error)) from error
        try:
            report = await self.reports.record(
                tenant_id=tenant_id,
                project_id=project.id,
                chapter_id=chapter_id,
                revision_id=revision_id,
                draft=draft,
                skill_plan_fingerprint=fingerprint,
                source_profile_version=str(context.get("source_profile_version") or "") or None,
                author="小说审读 Agent",
                idempotency_key=idempotency_key,
            )
            if run_id is not None:
                await self.runs.transition(
                    tenant_id=tenant_id, run_id=run_id, target=RunStatus.SUCCEEDED
                )
            return report
        except Exception as error:
            if run_id is not None:
                with suppress(Exception):
                    await self.runs.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code="novel_quality_persistence_failed",
                    )
            if isinstance(error, NovelQualityError):
                raise
            raise NovelQualityError(f"quality report could not be persisted: {error}") from error

    async def _context(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        chapter_id: str,
        revision_id: str,
    ) -> dict[str, object]:
        async with self.database.session() as session:
            revision = await session.get(NovelDocumentRevisionModel, revision_id)
            if (
                revision is None
                or revision.project_id != project.id
                or revision.chapter_id != chapter_id
            ):
                raise NovelQualityError("quality report revision is outside the requested chapter")
            blueprint = (
                await session.scalars(
                    select(NovelBlueprintModel).where(
                        NovelBlueprintModel.project_id == project.id,
                        NovelBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project.id)
                )
            ).one_or_none()
            revisions = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project.id
                    )
                )
            )
            anchors = (
                list(
                    await session.scalars(
                        select(NovelBlueprintAnchorModel).where(
                            NovelBlueprintAnchorModel.blueprint_id
                            == (blueprint.id if blueprint else "")
                        )
                    )
                )
                if blueprint
                else []
            )
            source_profile = (
                await session.scalars(
                    select(SourceProfileModel)
                    .where(
                        SourceProfileModel.tenant_id == tenant_id,
                        SourceProfileModel.project_id == project.id,
                        SourceProfileModel.decision == DistillationDecision.APPROVED,
                    )
                    .order_by(SourceProfileModel.version.desc())
                )
            ).first()
        chapter_ids = [
            str(dict(chapter).get("id"))
            for volume in (story_map.volumes if story_map else [])
            for chapter in list(dict(volume).get("chapters") or [])
        ]
        prior = latest_effective_revisions(
            revisions,
            chapter_ids=chapter_ids,
            before_chapter_id=chapter_id,
        )
        return {
            "project_id": project.id,
            "project_direction": dict(project.direction),
            "chapter_id": chapter_id,
            "revision_id": revision.id,
            "revision_number": revision.revision_number,
            "revision_source": revision.source,
            "blocks": list(revision.blocks),
            "story_map": list(story_map.volumes) if story_map else [],
            "prior_chapter_revisions": [
                {
                    "chapter_id": item.chapter_id,
                    "revision_id": item.id,
                    "revision_number": item.revision_number,
                    "source": item.source,
                    "blocks": list(item.blocks)[-12:],
                }
                for item in prior
            ],
            "blueprint_anchors": [
                {"kind": item.kind, "name": item.name, "payload": item.payload}
                for item in anchors
            ],
            "source_profile_version": source_profile.version if source_profile else None,
        }

    @staticmethod
    def _prompt(context: dict[str, object]) -> str:
        dimensions = [item.value for item in NovelQualityDimension]
        return (
            "Evaluate this NOVEL chapter candidate. Do not rewrite or adopt it. Assess every required "
            "dimension exactly once. Cite specific text or a concrete project fact in evidence; never "
            "invent source evidence. A source-boundary violation is blocking. Return JSON only with "
            "this schema: "
            '{"dimensions":[{"dimension":"...","verdict":"pass|revise|block",'
            '"score":1,"evidence":["..."],"diagnosis":"...","repair":"..."}],'
            '"summary":"..."}. '
            f"Required dimensions: {json.dumps(dimensions)}\n"
            f"Immutable review context: {json.dumps(context, ensure_ascii=False)}"
        )

    @staticmethod
    def parse(text: str) -> NovelQualityDraft:
        value = text.strip()
        fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
        if fenced:
            value = fenced[-1].strip()
        try:
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                raw = repair_json(value, schema=NovelQualityDraft.model_json_schema())
            if isinstance(raw, list):
                raw = {"dimensions": raw, "summary": "Quality review completed."}
            if isinstance(raw, dict):
                dimensions = raw.get("dimensions") or raw.get("assessments")
                if isinstance(dimensions, list):
                    normalized = []
                    for item in dimensions:
                        if not isinstance(item, dict):
                            normalized.append(item)
                            continue
                        normalized.append(
                            {
                                "dimension": item.get("dimension"),
                                "verdict": item.get("verdict"),
                                "score": item.get("score"),
                                "evidence": item.get("evidence"),
                                "diagnosis": item.get("diagnosis"),
                                "repair": item.get("repair") or item.get("recommendation"),
                            }
                        )
                    raw = {
                        "dimensions": normalized,
                        "summary": raw.get("summary") or raw.get("overall_summary"),
                    }
            return NovelQualityDraft.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
            raise NovelQualityError("审读 Agent 返回的质量报告不完整，正文与旧报告均未改变。") from error

    @staticmethod
    def _repair_prompt(raw_report: str) -> str:
        dimensions = [item.value for item in NovelQualityDimension]
        return (
            "Repair the following existing NOVEL quality assessment into the exact JSON contract. "
            "Do not re-review, rewrite, add prose, or change supported judgments. Remove commentary and "
            "extra fields. Include every required dimension exactly once. Each item requires dimension, "
            "verdict (pass|revise|block), integer score 1-5, non-empty evidence array, diagnosis, and repair. "
            f"Required dimensions: {json.dumps(dimensions)}. "
            'Return only {"dimensions":[...],"summary":"..."}. '
            f"Existing assessment: {raw_report}"
        )

    @staticmethod
    def _test_draft(context: dict[str, object]) -> NovelQualityDraft:
        text = "\n".join(str(item.get("text") or "") for item in context.get("blocks", []))
        return NovelQualityDraft(
            dimensions=tuple(
                NovelQualityAssessment(
                    dimension=dimension,
                    verdict=NovelQualityVerdict.REVISE,
                    score=3,
                    evidence=(text[:160] or "Development candidate contains no readable prose.",),
                    diagnosis=f"Development-mode review for {dimension.value} requires human verification.",
                    repair=f"Review and revise {dimension.value} before adoption.",
                )
                for dimension in NovelQualityDimension
            ),
            summary="Development-mode contract review completed; creative quality is not asserted.",
        )
