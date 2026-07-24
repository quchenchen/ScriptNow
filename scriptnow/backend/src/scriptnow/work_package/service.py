import json
import re
from contextlib import suppress
from dataclasses import dataclass

import json_repair
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from scriptnow.novel.domain import (
    NovelBlueprintAnchorModel,
    NovelBlueprintModel,
    NovelCandidateStatus,
    NovelStoryCoreCandidateModel,
)
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.image_supply import ImageGenerationError, ImageGenerationGateway
from scriptnow.platform.model_supply import CredentialCipher, CredentialError
from scriptnow.platform.models import (
    CoverArtifactModel,
    ImageModelModel,
    ProjectMedium,
    ProjectModel,
    RunStatus,
    TenantModel,
    TierModel,
    WorkPackageModel,
)
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.script.domain import (
    CandidateStatus,
    ScriptBlueprintAnchorModel,
    ScriptBlueprintModel,
    ScriptStoryCoreCandidateModel,
)


class WorkPackageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CoverOutputSpec:
    key: str
    platform: str
    width: int
    height: int
    ratio: str
    formats: tuple[str, ...]
    max_bytes: int | None
    note: str

    @property
    def image2_size(self) -> str:
        return f"{self.width}x{self.height}"


COVER_OUTPUT_SPECS: dict[str, CoverOutputSpec] = {
    "wattpad_hd": CoverOutputSpec(
        key="wattpad_hd",
        platform="Wattpad",
        width=1024,
        height=1600,
        ratio="16:25（约 2:3）",
        formats=("jpg", "png"),
        max_bytes=None,
        note="Wattpad 手机端高清推荐；兼容 512×800 的同比例缩放。",
    ),
    "wattpad_standard": CoverOutputSpec(
        key="wattpad_standard",
        platform="Wattpad",
        width=512,
        height=800,
        ratio="16:25（约 2:3）",
        formats=("jpg", "png"),
        max_bytes=None,
        note="欧美移动网文社区标准尺寸。",
    ),
    "webnovel": CoverOutputSpec(
        key="webnovel",
        platform="Webnovel（起点国际）",
        width=600,
        height=800,
        ratio="3:4",
        formats=("jpg",),
        max_bytes=5 * 1024 * 1024,
        note="严格保持 600×800，JPG 小于 5MB，避免平台强制裁剪。",
    ),
    "dreame_goodnovel": CoverOutputSpec(
        key="dreame_goodnovel",
        platform="Dreame / GoodNovel",
        width=600,
        height=800,
        ratio="3:4",
        formats=("jpg", "png"),
        max_bytes=None,
        note="出海女频平台常用规格；也可后续扩展为 750×1000。",
    ),
    "dreame_goodnovel_hd": CoverOutputSpec(
        key="dreame_goodnovel_hd",
        platform="Dreame / GoodNovel",
        width=750,
        height=1000,
        ratio="3:4",
        formats=("jpg", "png"),
        max_bytes=None,
        note="Dreame / GoodNovel 同比例高清规格。",
    ),
    "radish_inkitt": CoverOutputSpec(
        key="radish_inkitt",
        platform="Radish / Inkitt",
        width=600,
        height=900,
        ratio="2:3",
        formats=("jpg", "png"),
        max_bytes=None,
        note="常规竖版移动端网文比例。",
    ),
}

DEFAULT_COVER_OUTPUTS = ("wattpad_hd", "webnovel")


class CoverBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=10, max_length=800)
    setting: str = Field(min_length=5, max_length=800)
    visual_metaphor: str = Field(min_length=5, max_length=800)
    palette: tuple[str, ...] = Field(min_length=2, max_length=8)
    composition: str = Field(min_length=10, max_length=800)
    title_safe_area: str = Field(min_length=3, max_length=300)
    style: str = Field(min_length=3, max_length=500)
    forbidden_elements: tuple[str, ...] = Field(min_length=1, max_length=16)


class WorkPackageDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    synopsis: str = Field(min_length=100, max_length=2_000)
    tags: tuple[str, ...] = Field(min_length=3, max_length=12)
    cover_brief: CoverBrief


class WorkPackageService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.environment == "production"
        )

    async def generate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        idempotency_key: str,
        feedback: str | None,
    ) -> WorkPackageModel:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            tenant = await session.get(TenantModel, tenant_id)
            if project is None or project.tenant_id != tenant_id or tenant is None:
                raise WorkPackageError("project does not exist")
            facts = await self._facts(session, project)
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        architect = dict(dict(status["roles"])["architect"])
        if not architect.get("connected"):
            raise WorkPackageError(
                f"real packaging agent is unavailable: {architect.get('reason') or 'unknown'}"
            )
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=f"work-package:{idempotency_key}",
        )
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"work-package:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=16_000,
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
                role="architect",
                content=self._prompt(project, feedback),
                context_snapshot={"adopted_work_facts": facts},
            )
            await self._record_usage(reservation.id, tenant_id, run.id, result, attempt=1)
            try:
                draft = self.parse(result.text)
            except WorkPackageError:
                repaired = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    role="architect",
                    content=self._repair_prompt(project, result.text),
                    context_snapshot={"adopted_work_facts": facts},
                )
                await self._record_usage(reservation.id, tenant_id, run.id, repaired, attempt=2)
                draft = self.parse(repaired.text)
            await self.billing.finalize(reservation.id)
            package = await self._save(tenant_id, project, draft, feedback)
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            return package
        except Exception as error:
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="work_package_failed",
                )
            if isinstance(error, WorkPackageError | AgentRuntimeError):
                raise WorkPackageError(str(error)) from error
            raise WorkPackageError(f"invalid packaging agent output: {error}") from error

    async def _record_usage(
        self,
        reservation_id: str,
        tenant_id: str,
        run_id: str,
        result: AgentRuntimeResult,
        *,
        attempt: int,
    ) -> None:
        await self.billing.record_model_call(
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            run_id=run_id,
            framework_event_id=f"work-package:{run_id}:{attempt}",
            trace_id=run_id,
            agent_role="architect",
            model_key=result.model_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_price_per_million=result.input_price_per_million,
            output_price_per_million=result.output_price_per_million,
        )

    async def latest(self, *, tenant_id: str, project_id: str) -> WorkPackageModel | None:
        async with self.database.session() as session:
            return (
                await session.scalars(
                    select(WorkPackageModel)
                    .where(
                        WorkPackageModel.tenant_id == tenant_id,
                        WorkPackageModel.project_id == project_id,
                    )
                    .order_by(WorkPackageModel.version.desc())
                )
            ).first()

    async def covers(
        self, *, tenant_id: str, project_id: str
    ) -> list[CoverArtifactModel]:
        """Return persisted cover candidates newest first for a tenant-owned project."""
        async with self.database.session() as session:
            return list(
                (
                    await session.scalars(
                        select(CoverArtifactModel)
                        .where(
                            CoverArtifactModel.tenant_id == tenant_id,
                            CoverArtifactModel.project_id == project_id,
                        )
                        .order_by(CoverArtifactModel.created_at.desc())
                    )
                ).all()
            )

    async def generate_covers(
        self,
        *,
        tenant_id: str,
        project_id: str,
        image_model_id: str,
        output_keys: tuple[str, ...],
        prompt_override: str | None = None,
    ) -> list[CoverArtifactModel]:
        requested = output_keys or DEFAULT_COVER_OUTPUTS
        if len(requested) > 5 or len(set(requested)) != len(requested):
            raise WorkPackageError("choose between one and five unique cover sizes")
        try:
            specs = [COVER_OUTPUT_SPECS[key] for key in requested]
        except KeyError as error:
            raise WorkPackageError(f"unknown cover size: {error.args[0]}") from error
        async with self.database.session() as session:
            package = (
                await session.scalars(
                    select(WorkPackageModel)
                    .where(
                        WorkPackageModel.tenant_id == tenant_id,
                        WorkPackageModel.project_id == project_id,
                    )
                    .order_by(WorkPackageModel.version.desc())
                )
            ).first()
            tenant = await session.get(TenantModel, tenant_id)
            model = await session.get(ImageModelModel, image_model_id)
            model_tier = await session.get(TierModel, model.min_tier_id) if model else None
            tenant_tier = (
                (
                    await session.scalars(select(TierModel).where(TierModel.code == tenant.tier))
                ).one_or_none()
                if tenant
                else None
            )
            if package is None:
                raise WorkPackageError("generate work packaging before generating a cover")
            if model is None or not model.enabled or model_tier is None or tenant_tier is None:
                raise WorkPackageError("image model is unavailable")
            if tenant_tier.rank < model_tier.rank:
                raise WorkPackageError("current tier cannot use this image model")
        gateway = ImageGenerationGateway(
            self.database,
            CredentialCipher(lambda version: self.settings.credential_master_key),
        )
        effective_prompt = self.resolve_cover_prompt(package.cover_prompt, prompt_override)
        artifacts: list[CoverArtifactModel] = []
        for spec in specs:
            try:
                generated = await gateway.generate(
                    image_model_id=image_model_id,
                    prompt=effective_prompt,
                    aspect_ratio=spec.image2_size,
                )
            except (ImageGenerationError, CredentialError) as error:
                raise WorkPackageError(
                    f"{spec.platform} cover generation failed: {error}"
                ) from error
            async with self.database.session() as session:
                artifact = CoverArtifactModel(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    work_package_id=package.id,
                    image_model_id=image_model_id,
                    provider_request_id=generated.request_id,
                    image_url=generated.urls[0],
                    prompt_snapshot=effective_prompt,
                    platform_key=spec.key,
                    width=spec.width,
                    height=spec.height,
                    language=package.language,
                )
                session.add(artifact)
                await session.flush()
                artifacts.append(artifact)
        return artifacts

    @staticmethod
    def resolve_cover_prompt(agent_prompt: str, prompt_override: str | None) -> str:
        value = prompt_override.strip() if prompt_override is not None else agent_prompt.strip()
        if not value or len(value) > 20_000:
            raise WorkPackageError("cover prompt must contain 1-20000 characters")
        return value

    async def _save(
        self,
        tenant_id: str,
        project: ProjectModel,
        draft: WorkPackageDraft,
        feedback: str | None,
    ) -> WorkPackageModel:
        brief = draft.cover_brief.model_dump(mode="json")
        async with self.database.session() as session:
            version = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(WorkPackageModel.version), 0)).where(
                            WorkPackageModel.project_id == project.id
                        )
                    )
                    or 0
                )
                + 1
            )
            package = WorkPackageModel(
                tenant_id=tenant_id,
                project_id=project.id,
                version=version,
                title=draft.title,
                synopsis=draft.synopsis,
                tags=list(draft.tags),
                language=str(project.direction.get("language") or ""),
                cover_brief=brief,
                cover_prompt=self.compile_cover_prompt(
                    draft.cover_brief,
                    language=str(project.direction.get("language") or ""),
                ),
                feedback=feedback,
            )
            session.add(package)
            await session.flush()
            return package

    @staticmethod
    async def _facts(session, project: ProjectModel) -> dict[str, object]:
        if project.medium == ProjectMedium.NOVEL:
            core = (
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project.id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            blueprint = (
                await session.scalars(
                    select(NovelBlueprintModel).where(
                        NovelBlueprintModel.project_id == project.id,
                        NovelBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            anchors = (
                list(
                    await session.scalars(
                        select(NovelBlueprintAnchorModel).where(
                            NovelBlueprintAnchorModel.blueprint_id == blueprint.id
                        )
                    )
                )
                if blueprint
                else []
            )
            core_value = (
                {
                    "title": core.title,
                    "premise": core.premise,
                    "point_of_view": core.point_of_view,
                    "constraints": core.narrative_constraints,
                }
                if core
                else None
            )
        else:
            core = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project.id,
                        ScriptStoryCoreCandidateModel.status == CandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            blueprint = (
                await session.scalars(
                    select(ScriptBlueprintModel).where(
                        ScriptBlueprintModel.project_id == project.id,
                        ScriptBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            anchors = (
                list(
                    await session.scalars(
                        select(ScriptBlueprintAnchorModel).where(
                            ScriptBlueprintAnchorModel.blueprint_id == blueprint.id
                        )
                    )
                )
                if blueprint
                else []
            )
            core_value = (
                {
                    "title": core.title,
                    "concept": core.concept,
                    "details": core.details,
                    "angles": core.angles,
                }
                if core
                else None
            )
        if core_value is None:
            raise WorkPackageError("请先完成创意发散并采纳一个创作方向，再生成作品包装。")
        return {
            "medium": project.medium,
            "project_direction": project.direction,
            "story_core": core_value,
            "blueprint": [
                {"kind": item.kind, "name": item.name, "payload": item.payload} for item in anchors
            ],
        }

    @staticmethod
    def _prompt(project: ProjectModel, feedback: str | None) -> str:
        language = str(project.direction.get("language") or "zh-CN")
        return (
            "Act as the work packaging and cover-art director. Derive every claim from adopted work facts. "
            "Create a publication title, an approximately 200-word synopsis, searchable tags, and a concrete "
            "cover brief. The cover must communicate the work's distinctive protagonist, central conflict, "
            "world pressure and visual motif rather than generic genre imagery. Do not invent character names, "
            "objects, locations or plot facts. Reserve clean negative space for later title typography; ask the "
            "image model to render no letters, words, logos or watermarks. Return JSON only, no markdown.\n"
            f"Output language for title, synopsis and tags: {language}.\n"
            f"Medium: {project.medium}. Revision feedback: {feedback or 'none'}.\n"
            'Schema: {"title":"...","synopsis":"...","tags":["..."],"cover_brief":{'
            '"subject":"...","setting":"...","visual_metaphor":"...","palette":["..."],'
            '"composition":"...","title_safe_area":"...","style":"...",'
            '"forbidden_elements":["text","logo","watermark","..."]}}'
        )

    @staticmethod
    def _repair_prompt(project: ProjectModel, invalid_output: str) -> str:
        language = str(project.direction.get("language") or "zh-CN")
        return (
            "Repair the previous work-packaging response into the exact JSON schema below. "
            "Preserve valid creative content, add no new story facts, and fill every required field. "
            "Return one JSON object only: no markdown, comments, trailing commas, or explanatory text. "
            f"All user-facing strings must use {language}.\n"
            'Required schema: {"title":"1-240 chars","synopsis":"100-2000 chars",'
            '"tags":["3-12 tags"],"cover_brief":{"subject":"10-800 chars",'
            '"setting":"5-800 chars","visual_metaphor":"5-800 chars",'
            '"palette":["2-8 colors"],"composition":"10-800 chars",'
            '"title_safe_area":"3-300 chars","style":"3-500 chars",'
            '"forbidden_elements":["1-16 items"]}}\n'
            f"Previous invalid response:\n{invalid_output[:12_000]}"
        )

    @staticmethod
    def compile_cover_prompt(brief: CoverBrief, *, language: str = "zh-CN") -> str:
        """Compile Agent-authored semantics without adding story facts."""
        return (
            f"Book or screenplay cover artwork. Subject: {brief.subject}. Setting: {brief.setting}. "
            f"Central visual metaphor: {brief.visual_metaphor}. Art direction: {brief.style}. "
            f"Composition: {brief.composition}. Reserve title-safe negative space: {brief.title_safe_area}. "
            f"Color palette: {', '.join(brief.palette)}. Avoid: {', '.join(brief.forbidden_elements)}. "
            f"The publication language is {language}; preserve culturally appropriate visual cues. "
            "No text, no letters, no typography, no logo, no watermark. Professional publishing cover, "
            "single coherent composition, high detail."
        )

    @staticmethod
    def parse(text: str) -> WorkPackageDraft:
        value = text.strip()
        fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
        if fenced:
            value = fenced[-1].strip()
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            try:
                payload = json_repair.loads(value, schema=WorkPackageDraft.model_json_schema())
            except Exception as error:
                raise WorkPackageError(
                    "包装 Agent 返回的内容不完整，系统未能安全整理。请重新生成一次。"
                ) from error
        try:
            return WorkPackageDraft.model_validate(payload)
        except ValidationError as error:
            raise WorkPackageError("包装 Agent 返回的内容缺少必要信息，请重新生成一次。") from error
