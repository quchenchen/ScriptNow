import json
import logging
import re
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from scriptnow.novel.domain import (
    NovelBlueprintAnchorDraft,
    NovelBlueprintDraft,
    NovelCandidateStatus,
    NovelStoryCoreCandidateModel,
)
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, RagChunkModel, RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator


class NovelBlueprintError(RuntimeError):
    pass


class _Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=120)
    kind: str = Field(pattern=r"^(world|character|relationship|character_arc|plot|foreshadow|motif)$")
    name: str = Field(min_length=2, max_length=200)
    payload: dict[str, object]


logger = logging.getLogger(__name__)


class _Payload(BaseModel):
    # Architect models may include useful envelope metadata (title, structure,
    # volumes). Anchors remain the sole accepted persistence contract.
    model_config = ConfigDict(extra="ignore")

    anchors: tuple[_Anchor, ...] = Field(min_length=12, max_length=40)

    @model_validator(mode="after")
    def validate_coverage(self) -> "_Payload":
        kinds = {item.kind for item in self.anchors}
        required = {"world", "character", "relationship", "character_arc", "plot", "foreshadow", "motif"}
        missing = required - kinds
        if missing:
            raise ValueError(f"incomplete novel blueprint: missing {', '.join(sorted(missing))}")
        if len({item.id for item in self.anchors}) != len(self.anchors):
            raise ValueError("novel blueprint anchor IDs must be unique")
        return self


class NovelBlueprintGenerator:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
        )

    async def generate(
        self,
        *,
        tenant_id: str,
        project: ProjectModel,
        idempotency_key: str,
        feedback: str | None,
    ) -> NovelBlueprintDraft:
        status = await self.runtime.status(tenant_id=tenant_id, project_id=project.id)
        architect = dict(dict(status["roles"])["architect"])
        if not architect.get("connected"):
            raise NovelBlueprintError(
                f"real architect runtime is unavailable: {architect.get('reason') or 'unknown'}"
            )
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project.id,
            idempotency_key=f"novel-blueprint:{idempotency_key}",
        )
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            core = (
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project.id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            if tenant is None or core is None:
                raise NovelBlueprintError("tenant and adopted novel direction are required")
            chunks = list(
                await session.scalars(
                    select(RagChunkModel)
                    .where(
                        RagChunkModel.tenant_id == tenant_id,
                        RagChunkModel.project_id == project.id,
                    )
                    .order_by(RagChunkModel.ordinal)
                )
            )
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"novel-blueprint:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=self.settings.novel_blueprint_reserved_tokens,
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        try:
            result = await self.runtime.generate(
                tenant_id=tenant_id,
                run_id=run.id,
                role="architect",
                content=self._prompt(project, core, feedback),
                context_snapshot={
                    "project_id": project.id,
                    "source_mode": project.source_mode,
                    "source_excerpts": self._source_excerpts(chunks),
                },
            )
            payload = self.parse(result.text)
            await self._record_usage(reservation.id, tenant_id, run.id, result)
            await self.billing.finalize(reservation.id)
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            return NovelBlueprintDraft(
                anchors=tuple(
                    NovelBlueprintAnchorDraft(
                        id=item.id, kind=item.kind, name=item.name, payload=item.payload
                    )
                    for item in payload.anchors
                )
            )
        except Exception as error:
            logger.exception(
                "novel blueprint generation failed",
                extra={"run_id": run.id, "project_id": project.id},
            )
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="novel_blueprint_failed",
                )
            if isinstance(error, NovelBlueprintError):
                raise
            if isinstance(error, AgentRuntimeError):
                raise NovelBlueprintError(str(error)) from error
            raise NovelBlueprintError(f"invalid architect output: {error}") from error

    async def _record_usage(
        self, reservation_id: str, tenant_id: str, run_id: str, result: AgentRuntimeResult
    ) -> None:
        await self.billing.record_model_call(
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            run_id=run_id,
            framework_event_id=f"novel-blueprint:{run_id}",
            trace_id=run_id,
            agent_role="architect",
            model_key=result.model_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            input_price_per_million=result.input_price_per_million,
            output_price_per_million=result.output_price_per_million,
        )

    @staticmethod
    def _source_excerpts(chunks: list[RagChunkModel]) -> list[dict[str, object]]:
        if not chunks:
            return []
        indexes = sorted({round(index * (len(chunks) - 1) / 23) for index in range(min(24, len(chunks)))})
        return [
            {"ordinal": chunks[index].ordinal, "content": chunks[index].content[:1_600]}
            for index in indexes
        ]

    @staticmethod
    def _prompt(
        project: ProjectModel, core: NovelStoryCoreCandidateModel, feedback: str | None
    ) -> str:
        language = str(project.direction.get("language") or "zh-CN")
        return (
            "Build a production-ready NOVEL blueprint from the adopted direction and source evidence. "
            "Do not use screenplay scenes, episodes, runtime, or camera language. Create 12-24 concise, "
            "specific anchors covering every required kind: world, character, relationship, character_arc, "
            "plot, foreshadow, motif. Include at least 3 characters, 2 relationships, 2 character arcs, "
            "3 plot movements and 2 foreshadow plans. Payloads must expose actionable detail: description; "
            "characters need identity/traits/want/need; relationships need movement and conflict; arcs need "
            "start/midpoint/end; plots need cause/escalation/consequence; foreshadows need setup/payoff/status; "
            "world rules need cost and dramatic consequence. Preserve source facts when supplied and clearly "
            "avoid unsupported claims. Return JSON only with no markdown.\n"
            f"Creative language: {language}. Every user-facing string must use that language.\n"
            f"Adopted direction: {core.title}\nPremise: {core.premise}\n"
            f"Narrative constraints: {json.dumps(core.narrative_constraints, ensure_ascii=False)}\n"
            f"Project direction: {json.dumps(project.direction, ensure_ascii=False)}\n"
            f"Revision feedback: {feedback or 'none'}\n"
            'Schema: {"anchors":[{"id":"kind:stable-key","kind":"world|character|relationship|'
            'character_arc|plot|foreshadow|motif","name":"...","payload":{"description":"..."}}]}'
        )

    @staticmethod
    def parse(text: str) -> _Payload:
        value = text.strip()
        fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
        if fenced:
            value = fenced[-1].strip()

        # Attempt 1: strict JSON parse
        first_error: str | None = None
        try:
            return _Payload.model_validate(json.loads(value))
        except ValidationError as error:
            first_error = str(error)
        except json.JSONDecodeError:
            pass

        # Attempt 2: JSON repair with schema
        try:
            repaired = repair_json(value, schema=_Payload.model_json_schema())
            return _Payload.model_validate(repaired)
        except (ValidationError, ValueError, TypeError):
            pass

        # Attempt 3: extract anchors from any JSON structure
        try:
            raw = repair_json(value)
            if isinstance(raw, dict):
                raw_anchors = raw.get("anchors", raw.get("data", raw))
                if isinstance(raw_anchors, list):
                    cleaned = []
                    for item in raw_anchors:
                        if not isinstance(item, dict):
                            continue
                        aid = str(item.get("id", item.get("name", "")))
                        kind = str(item.get("kind", item.get("type", "")))
                        name = str(item.get("name", item.get("label", "")))
                        payload = item.get("payload", item.get("data", item))
                        if not isinstance(payload, dict):
                            payload = {"description": str(payload)[:2000]}
                        if aid and kind and name:
                            cleaned.append({"id": aid, "kind": kind, "name": name, "payload": payload})
                    if len(cleaned) >= 8:
                        return _Payload.model_validate({"anchors": cleaned})
        except Exception:
            pass

        raise NovelBlueprintError(
            first_error or "蓝图格式需要整理，旧版本已保留，请重新生成。"
        )
