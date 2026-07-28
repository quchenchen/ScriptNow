import json
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from scriptnow.novel.cross_cultural_recreation.service import (
    CrossCulturalRecreationService,
)
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RagChunkModel, RunStatus
from scriptnow.platform.run_coordinator import RunCoordinator


class RecreationGenerationError(RuntimeError):
    pass


class SourceStoryModelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_summary: str = Field(min_length=30)
    story_genes: list[dict[str, object]] = Field(min_length=3)
    cultural_gaps: list[dict[str, object]] = Field(min_length=1)
    protected_elements: list[str] = Field(min_length=1)
    uncertainties: list[str] = Field(default_factory=list)


class StrategyCandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=160)
    target_premise: str = Field(min_length=40)
    recreation_thesis: str = Field(min_length=30)
    localization_decisions: list[dict[str, object]] = Field(min_length=3)
    retained_genes: list[str] = Field(min_length=2)
    risks: list[str] = Field(min_length=1)
    pilot_unit: str = Field(min_length=10)


class StrategyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[StrategyCandidatePayload] = Field(min_length=3, max_length=3)


class PilotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_title: str = Field(min_length=2, max_length=200)
    rationale: str = Field(min_length=20)
    target_language_draft: str = Field(min_length=300)
    change_notes: list[dict[str, object]] = Field(min_length=2)
    gene_trace: list[dict[str, object]] = Field(min_length=2)
    open_questions: list[str] = Field(default_factory=list)


class ScaleWorkPackagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: str | int
    chapter_number: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1)
    target_words: int | None = Field(default=None, ge=1)
    source_scope: str = Field(min_length=1)
    narrative_function: str = Field(min_length=1)
    target_design: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    protected_genes: list[str] = Field(default_factory=list)
    continuity_inputs: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)


class ScalePlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_story_bible: dict[str, object]
    character_migrations: list[dict[str, object]] = Field(min_length=1)
    work_packages: list[ScaleWorkPackagePayload] = Field(min_length=1)
    continuity_rules: list[str] = Field(min_length=1)
    quality_gates: list[dict[str, object]] = Field(min_length=1)
    unresolved_decisions: list[str] = Field(default_factory=list)


class ProductionUnitPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_package_key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    target_language_draft: str = Field(min_length=300)
    recreation_rationale: list[dict[str, object]] = Field(min_length=1)
    gene_trace: list[dict[str, object]] = Field(min_length=1)
    continuity_updates: list[dict[str, object]] = Field(default_factory=list)
    quality_self_check: list[dict[str, object]] = Field(min_length=1)
    open_questions: list[str] = Field(default_factory=list)


class CrossCulturalRecreationGenerator:
    def __init__(self, database: Database, runtime: AgentRuntime) -> None:
        self.database = database
        self.runtime = runtime
        self.runs = RunCoordinator(database)

    async def analyze_source(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        target_contract: dict[str, object],
        run_id: str | None = None,
    ) -> dict[str, object]:
        source = await self._source_text(tenant_id=tenant_id, project_id=project.id)
        if not source:
            raise RecreationGenerationError("尚未形成可分析的源作品文本，请先完成素材上传与索引")
        prompt = (
            "You are the source-story analyst in a cross-cultural story recreation team. "
            "This is NOT translation. Extract the narrative functions that must be preserved "
            "before any cultural reconstruction. Return JSON only with exactly these keys: "
            "story_summary, story_genes, cultural_gaps, protected_elements, uncertainties. "
            "Each story_genes item must explain name, narrative_function, evidence. Each "
            "cultural_gaps item must explain source_element, implied_social_knowledge, "
            "reader_failure_risk, and possible treatment without selecting a final treatment. "
            f"Target hypothesis: {json.dumps(target_contract, ensure_ascii=False)}\n"
            f"Source evidence:\n{source}"
        )
        return await self._generate(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"cross-cultural-source:{idempotency_key}",
            role="director",
            stage="cross_cultural_source_analysis",
            prompt=prompt,
            payload_type=SourceStoryModelPayload,
            run_id=run_id,
        )

    async def generate_strategies(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        source_model: dict[str, object],
        target_contract: dict[str, object],
        feedback: str | None,
        run_id: str | None = None,
    ) -> tuple[dict[str, object], ...]:
        prompt = (
            "You are the lead story architect for cross-cultural recreation. This is NOT "
            "translation and must not preserve sentences. Propose exactly three genuinely "
            "different recreation strategies that preserve adopted story genes while rebuilding "
            "social causality, character motivation, cultural scripts, genre promise, and original "
            "target-language narration. Return JSON only as {\"candidates\": [...]}. Every "
            "candidate must contain title, target_premise, recreation_thesis, "
            "localization_decisions (each with source_function, target_carrier, causal_reason), "
            "retained_genes, risks, pilot_unit. Do not silently change protected elements.\n"
            f"Source story model: {json.dumps(source_model, ensure_ascii=False)}\n"
            f"Target story contract: {json.dumps(target_contract, ensure_ascii=False)}\n"
            f"Author feedback: {feedback or 'none'}"
        )
        payload = await self._generate(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"cross-cultural-strategy:{idempotency_key}",
            role="architect",
            stage="cross_cultural_strategy",
            prompt=prompt,
            payload_type=StrategyPayload,
            structure_error=("创作团队返回的三套策略缺少必要结构，请保留反馈后重新生成"),
            run_id=run_id,
        )
        return tuple(dict(item) for item in payload["candidates"])

    async def generate_pilot(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        source_model: dict[str, object],
        target_contract: dict[str, object],
        strategy: dict[str, object],
        feedback: str | None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        source = await self._source_text(tenant_id=tenant_id, project_id=project.id)
        prompt = (
            "You are the target-language novelist in a cross-cultural story recreation "
            "team. This is an ORIGINAL RECREATION PILOT, not translation. Write one "
            "representative pilot unit in the target language. Preserve adopted story genes "
            "and the selected strategy, but rebuild cultural causality and natural target-reader "
            "experience. Return JSON only with unit_title, rationale, target_language_draft, "
            "change_notes, gene_trace, open_questions. Each change_notes item must explain "
            "source_function, recreation_decision, target_reader_effect. Each gene_trace item "
            "must explain gene, realization, evidence_in_draft. Do not silently alter protected "
            "elements.\n"
            f"Source story model: {json.dumps(source_model, ensure_ascii=False)}\n"
            f"Target story contract: {json.dumps(target_contract, ensure_ascii=False)}\n"
            f"Adopted strategy: {json.dumps(strategy, ensure_ascii=False)}\n"
            f"Author feedback: {feedback or 'none'}\n"
            f"Source evidence:\n{source}"
        )
        return await self._generate(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"cross-cultural-pilot:{idempotency_key}",
            role="writer",
            stage="cross_cultural_pilot",
            prompt=prompt,
            payload_type=PilotPayload,
            run_id=run_id,
        )

    async def generate_scale_plan(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        source_model: dict[str, object],
        target_contract: dict[str, object],
        strategy: dict[str, object],
        pilot: dict[str, object],
        feedback: str | None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        prompt = (
            "You are the production architect for a cross-cultural story recreation. "
            "The author has approved a representative pilot. Build the production blueprint "
            "for recreating the complete source work; do not write the whole manuscript yet. "
            "Return JSON only with target_story_bible, character_migrations, work_packages, "
            "continuity_rules, quality_gates, unresolved_decisions. The target_story_bible "
            "must cover setting, institutions, relationship boundaries, genre rules, target "
            "voice, protected story genes, and forbidden changes. Each character_migrations "
            "item must explain character, source_pressure, target_pressure, behavior_changes, "
            "relationship_effect, arc_invariant. Derive work_packages from the source work "
            "rather than assuming a fixed chapter count. One work package must represent "
            "exactly one deliverable chapter so generation, review, manual revision and "
            "adoption can recover independently. Each item must contain order, chapter_number, "
            "title, and may contain target_words only when the approved project contract "
            "defines a chapter budget; never invent a fixed word count. It must also contain "
            "source_scope, narrative_function, target_design, dependencies, protected_genes, "
            "continuity_inputs, acceptance_criteria. Each quality_gates item must contain "
            "name, evidence, pass_condition and reviewer_role. This is not translation and "
            "must preserve the author's confirmed decisions.\n"
            f"Source story model: {json.dumps(source_model, ensure_ascii=False)}\n"
            f"Target story contract: {json.dumps(target_contract, ensure_ascii=False)}\n"
            f"Adopted strategy: {json.dumps(strategy, ensure_ascii=False)}\n"
            f"Adopted pilot: {json.dumps(pilot, ensure_ascii=False)}\n"
            f"Author feedback: {feedback or 'none'}"
        )
        return await self._generate(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"cross-cultural-scale-plan:{idempotency_key}",
            role="architect",
            stage="cross_cultural_scale_plan",
            prompt=prompt,
            payload_type=ScalePlanPayload,
            run_id=run_id,
        )

    async def generate_production_unit(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        source_model: dict[str, object],
        target_contract: dict[str, object],
        strategy: dict[str, object],
        pilot: dict[str, object],
        scale_plan: dict[str, object],
        work_package: dict[str, object],
        adopted_units: list[dict[str, object]],
        feedback: str | None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        source = await self._source_text(tenant_id=tenant_id, project_id=project.id)
        work_package_key = str(work_package.get("order", "")).strip()
        if not work_package_key:
            raise RecreationGenerationError("整书方案中的工作包缺少稳定编号")
        prior_continuity = [
            {
                "work_package_key": item.get("work_package_key"),
                "title": item.get("title"),
                "continuity_updates": item.get("continuity_updates", []),
                "open_questions": item.get("open_questions", []),
            }
            for item in adopted_units
        ]
        prompt = (
            "You are the target-language lead novelist producing one approved work package "
            "of a cross-cultural story recreation. This is original target-market writing, "
            "not sentence-aligned translation. Write only the requested work package. Obey "
            "the adopted target story bible, protected genes, package dependencies, accepted "
            "earlier continuity, and author feedback. Do not resolve later packages early. "
            "Return JSON only with work_package_key, title, target_language_draft, "
            "recreation_rationale, gene_trace, continuity_updates, quality_self_check, "
            "open_questions. work_package_key must exactly equal the requested key. Each "
            "recreation_rationale item explains source_function, target_realization and "
            "reader_effect. Each gene_trace item explains gene and evidence_in_draft. Each "
            "quality_self_check item explains gate, evidence and result. Never hide a failed "
            "gate by claiming success.\n"
            f"Requested work package key: {work_package_key}\n"
            f"Requested work package: {json.dumps(work_package, ensure_ascii=False)}\n"
            f"Source story model: {json.dumps(source_model, ensure_ascii=False)}\n"
            f"Target story contract: {json.dumps(target_contract, ensure_ascii=False)}\n"
            f"Adopted strategy: {json.dumps(strategy, ensure_ascii=False)}\n"
            f"Adopted representative pilot: {json.dumps(pilot, ensure_ascii=False)}\n"
            f"Adopted scale plan: {json.dumps(scale_plan, ensure_ascii=False)}\n"
            f"Accepted earlier continuity: {json.dumps(prior_continuity, ensure_ascii=False)}\n"
            f"Author feedback: {feedback or 'none'}\n"
            f"Source evidence:\n{source}"
        )
        payload = await self._generate(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=(f"cross-cultural-production:{work_package_key}:{idempotency_key}"),
            role="writer",
            stage="cross_cultural_production",
            prompt=prompt,
            payload_type=ProductionUnitPayload,
            run_id=run_id,
        )
        if payload["work_package_key"] != work_package_key:
            correction_prompt = (
                "The previous candidate does not belong to the requested work package. "
                "Rewrite it as the requested package instead of merely changing its key. "
                "Obey the requested package scope, dependencies, target design, acceptance "
                "criteria and accepted earlier continuity. Do not resolve later packages. "
                "Return JSON only using the ProductionUnitPayload schema. "
                f"work_package_key must be exactly {work_package_key}.\n"
                f"Requested work package: {json.dumps(work_package, ensure_ascii=False)}\n"
                f"Target story contract: {json.dumps(target_contract, ensure_ascii=False)}\n"
                f"Adopted scale plan: {json.dumps(scale_plan, ensure_ascii=False)}\n"
                f"Accepted earlier continuity: {json.dumps(prior_continuity, ensure_ascii=False)}\n"
                f"Author feedback: {feedback or 'none'}\n"
                f"Rejected candidate: {json.dumps(payload, ensure_ascii=False)}"
            )
            payload = await self._generate(
                tenant_id=tenant_id,
                project_id=project.id,
                idempotency_key=(
                    "cross-cultural-production:"
                    f"{work_package_key}:{idempotency_key}:identity-repair"
                ),
                role="writer",
                stage="cross_cultural_production_identity_repair",
                prompt=correction_prompt,
                payload_type=ProductionUnitPayload,
                run_id=run_id,
            )
            if payload["work_package_key"] != work_package_key:
                raise RecreationGenerationError("创作团队返回了错误的工作包编号")
        self._validate_target_language(
            draft=str(payload["target_language_draft"]),
            target_language=str(target_contract.get("target_language", "")),
        )
        return payload

    @staticmethod
    def _validate_target_language(*, draft: str, target_language: str) -> None:
        """Reject structurally valid drafts written in the wrong script.

        This is deliberately a narrow safety gate rather than language detection:
        locale policy still comes from the project contract, while the gate only
        catches unmistakable script mismatches before they enter continuity.
        """
        locale = target_language.strip().lower()
        if not draft.strip() or not locale:
            return
        letters = [character for character in draft if character.isalpha()]
        if not letters:
            raise RecreationGenerationError("候选稿没有可识别的正文内容")
        han_count = sum("\u4e00" <= character <= "\u9fff" for character in letters)
        latin_count = sum(("a" <= character.lower() <= "z") for character in letters)
        if locale.startswith("en") and han_count > latin_count:
            raise RecreationGenerationError("候选稿未使用项目设定的目标创作语言，请重新生成")
        if locale.startswith(("zh", "ja")) and latin_count > len(letters) * 0.9:
            raise RecreationGenerationError("候选稿未使用项目设定的目标创作语言，请重新生成")

    async def _source_text(self, *, tenant_id: str, project_id: str) -> str:
        async with self.database.session() as session:
            chunks = list(
                await session.scalars(
                    select(RagChunkModel)
                    .where(
                        RagChunkModel.tenant_id == tenant_id,
                        RagChunkModel.project_id == project_id,
                    )
                    .order_by(RagChunkModel.ordinal)
                )
            )
        return "\n\n".join(f"[source {item.ordinal}]\n{item.content}" for item in chunks)

    async def _generate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        idempotency_key: str,
        role: str,
        stage: str,
        prompt: str,
        payload_type: type[BaseModel],
        run_id: str | None = None,
        structure_error: str = ("创作团队返回的内容缺少必要结构，请保留当前输入后重新生成"),
    ) -> dict[str, object]:
        owns_run = run_id is None
        if owns_run:
            run = await self.runs.enqueue(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
            )
            run_id = run.id
            await self.runs.transition(
                tenant_id=tenant_id,
                run_id=run_id,
                target=RunStatus.RUNNING,
            )
        assert run_id is not None
        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run_id,
                role=role,
                content=prompt,
                context_snapshot={
                    "project_id": project_id,
                    "workflow_kind": "cross_cultural_recreation",
                    "stage": stage,
                },
                stage_override=stage,
            )
            try:
                payload = self._validated_payload(
                    payload_type,
                    result.text,
                    error_message=structure_error,
                )
            except RecreationGenerationError:
                repair_prompt = (
                    "Repair the following model output so it conforms exactly to the supplied "
                    "JSON Schema. Preserve the creative content and decisions; only repair JSON "
                    "syntax, field names, missing required fields, and incompatible field types. "
                    "Return JSON only, with no markdown fence or explanation.\n"
                    f"JSON Schema: {json.dumps(payload_type.model_json_schema(), ensure_ascii=False)}\n"
                    f"Model output: {result.text}"
                )
                repaired = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    role=role,
                    content=repair_prompt,
                    context_snapshot={
                        "project_id": project_id,
                        "workflow_kind": "cross_cultural_recreation",
                        "stage": f"{stage}_structure_repair",
                    },
                    stage_override=stage,
                )
                payload = self._validated_payload(
                    payload_type,
                    repaired.text,
                    error_message=structure_error,
                )
            if owns_run:
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    target=RunStatus.SUCCEEDED,
                )
            return payload
        except (AgentRuntimeError, RecreationGenerationError) as error:
            if owns_run:
                with suppress(Exception):
                    await self.runs.transition(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        target=RunStatus.FAILED,
                        error_code="cross_cultural_generation_failed",
                    )
                with suppress(Exception):
                    await CrossCulturalRecreationService(
                        self.database
                    ).record_generation_failure(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        stage=stage,
                        run_id=run_id,
                        message=str(error),
                    )
            raise RecreationGenerationError(str(error)) from error

    @staticmethod
    def _parse(raw: str) -> dict[str, object]:
        value = raw.strip()
        if value.startswith("```"):
            value = value.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            payload = repair_json(value)
        except (json.JSONDecodeError, ValueError) as error:
            raise RecreationGenerationError("Agent 返回的结构不完整") from error
        if not isinstance(payload, dict):
            raise RecreationGenerationError("Agent 返回的内容不是对象")
        return payload

    @classmethod
    def _validated_payload(
        cls,
        payload_type: type[BaseModel],
        raw: str,
        *,
        error_message: str = ("创作团队返回的内容缺少必要结构，请保留当前输入后重新生成"),
    ) -> dict[str, object]:
        try:
            return payload_type.model_validate(cls._parse(raw)).model_dump()
        except ValidationError as error:
            raise RecreationGenerationError(error_message) from error
