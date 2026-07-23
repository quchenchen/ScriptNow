from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from scriptflow_v7.novel.domain import NovelDocumentRevisionModel, NovelQualityReportModel
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import ProjectMedium, ProjectModel

NOVEL_QUALITY_RUBRIC_VERSION = "novel-chapter-quality-v1"


class NovelQualityDimension(StrEnum):
    CHARACTER_AGENCY = "character_agency"
    SCENE_CAUSALITY = "scene_causality"
    RELATIONSHIP_PROGRESSION = "relationship_progression"
    NARRATIVE_VOICE = "narrative_voice"
    CONTINUITY = "continuity"
    SOURCE_BOUNDARY = "source_boundary"
    CHAPTER_PROPULSION = "chapter_propulsion"
    PROSE_TEXTURE = "prose_texture"


class NovelQualityVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


class NovelQualityReadiness(StrEnum):
    READY = "ready"
    REVISION_REQUIRED = "revision_required"
    BLOCKED = "blocked"


class NovelQualityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: NovelQualityDimension
    verdict: NovelQualityVerdict
    score: int = Field(ge=1, le=5)
    evidence: tuple[str, ...] = Field(min_length=1)
    diagnosis: str = Field(min_length=2)
    repair: str = Field(min_length=2)


class NovelQualityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimensions: tuple[NovelQualityAssessment, ...]
    summary: str = Field(min_length=2)

    @model_validator(mode="after")
    def require_complete_rubric(self) -> "NovelQualityDraft":
        actual = [item.dimension for item in self.dimensions]
        required = set(NovelQualityDimension)
        if len(actual) != len(required) or set(actual) != required:
            raise ValueError("every Novel quality dimension is required exactly once")
        return self

    @property
    def readiness(self) -> NovelQualityReadiness:
        verdicts = {item.verdict for item in self.dimensions}
        if NovelQualityVerdict.BLOCK in verdicts:
            return NovelQualityReadiness.BLOCKED
        if NovelQualityVerdict.REVISE in verdicts or self.maturity_score < 80:
            return NovelQualityReadiness.REVISION_REQUIRED
        return NovelQualityReadiness.READY

    @property
    def maturity_score(self) -> int:
        return round(sum(item.score for item in self.dimensions) / (len(self.dimensions) * 5) * 100)


class NovelQualityError(RuntimeError):
    pass


class NovelQualityService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def record(
        self,
        *,
        tenant_id: str,
        project_id: str,
        chapter_id: str,
        revision_id: str,
        draft: NovelQualityDraft,
        skill_plan_fingerprint: str,
        source_profile_version: str | None,
        author: str,
        idempotency_key: str,
    ) -> NovelQualityReportModel:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != tenant_id
                or project.medium != ProjectMedium.NOVEL
            ):
                raise NovelQualityError("Novel project is outside the requested tenant")
            existing = (
                await session.scalars(
                    select(NovelQualityReportModel).where(
                        NovelQualityReportModel.project_id == project_id,
                        NovelQualityReportModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            revision = await session.get(NovelDocumentRevisionModel, revision_id)
            if (
                revision is None
                or revision.project_id != project_id
                or revision.chapter_id != chapter_id
            ):
                raise NovelQualityError("quality report revision is outside the requested chapter")
            report = NovelQualityReportModel(
                tenant_id=tenant_id,
                project_id=project_id,
                chapter_id=chapter_id,
                revision_id=revision_id,
                rubric_version=NOVEL_QUALITY_RUBRIC_VERSION,
                source_profile_version=source_profile_version,
                skill_plan_fingerprint=skill_plan_fingerprint,
                dimensions=[item.model_dump(mode="json") for item in draft.dimensions],
                overall_status=draft.readiness,
                maturity_score=draft.maturity_score,
                summary=draft.summary,
                author=author,
                idempotency_key=idempotency_key,
            )
            session.add(report)
            await session.flush()
            return report

    async def history(
        self, *, tenant_id: str, project_id: str, chapter_id: str
    ) -> list[NovelQualityReportModel]:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if project is None or project.tenant_id != tenant_id:
                raise NovelQualityError("Novel project is outside the requested tenant")
            return list(
                await session.scalars(
                    select(NovelQualityReportModel)
                    .where(
                        NovelQualityReportModel.project_id == project_id,
                        NovelQualityReportModel.chapter_id == chapter_id,
                    )
                    .order_by(NovelQualityReportModel.created_at.desc())
                )
            )
