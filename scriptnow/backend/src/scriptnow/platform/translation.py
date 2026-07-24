import json
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict, Field

from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.translation_contracts import TranslationError, TranslationUnit


class _TranslatedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=80)
    text: str


class _TranslationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titles: dict[str, str]
    blocks: tuple[_TranslatedBlock, ...]


class FaithfulTranslationService:
    """Translate export-only content without changing adopted domain revisions."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.environment == "production"
        )

    async def translate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_language: str,
        target_language: str,
        units: tuple[TranslationUnit, ...],
        idempotency_key: str,
    ) -> tuple[TranslationUnit, ...]:
        target_language = target_language.strip()
        if not target_language:
            raise TranslationError("target language is required")
        if source_language.strip().casefold() == target_language.casefold():
            raise TranslationError("target language must differ from the creative language")
        if not units:
            return ()

        status = await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        writer = dict(dict(status["roles"])["writer"])
        if not writer.get("connected"):
            raise TranslationError(
                f"translation runtime is unavailable: {writer.get('reason') or 'unknown'}"
            )
        run = await self.runs.enqueue(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=f"faithful-translation:{idempotency_key}",
        )
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            if tenant is None:
                raise TranslationError("tenant does not exist")
        source_characters = sum(
            len(str(value))
            for unit in units
            for value in (*unit.titles.values(), *(block.get("text", "") for block in unit.blocks))
        )
        reserved_tokens = min(
            self.settings.translation_max_reserved_tokens,
            max(
                self.settings.translation_min_reserved_tokens,
                int(source_characters * self.settings.translation_token_reserve_ratio),
            ),
        )
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"faithful-translation:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=reserved_tokens,
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        translated: list[TranslationUnit] = []
        try:
            for index, unit in enumerate(units):
                result = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    role="writer",
                    stage_override="translation",
                    content=self._prompt(
                        source_language=source_language,
                        target_language=target_language,
                        unit=unit,
                    ),
                    context_snapshot={
                        "project_id": project_id,
                        "translation_mode": "faithful",
                        "source_language": source_language,
                        "target_language": target_language,
                        "unit_index": index,
                    },
                )
                translated.append(self._parse(result.text, original=unit))
                await self.billing.record_model_call(
                    reservation_id=reservation.id,
                    tenant_id=tenant_id,
                    run_id=run.id,
                    framework_event_id=f"translation:{run.id}:{index}",
                    trace_id=run.id,
                    agent_role="writer",
                    model_key=result.model_key,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    input_price_per_million=result.input_price_per_million,
                    output_price_per_million=result.output_price_per_million,
                )
            await self.billing.finalize(reservation.id)
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
            )
            return tuple(translated)
        except Exception as error:
            with suppress(Exception):
                await self.billing.release(reservation.id)
            with suppress(Exception):
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code="faithful_translation_failed",
                )
            if isinstance(error, TranslationError):
                raise
            if isinstance(error, AgentRuntimeError):
                raise TranslationError(str(error)) from error
            raise TranslationError(f"translation could not be safely completed: {error}") from error

    @staticmethod
    def _prompt(
        *, source_language: str, target_language: str, unit: TranslationUnit
    ) -> str:
        payload = {"titles": unit.titles, "blocks": list(unit.blocks)}
        return (
            "You are performing faithful literary translation for an export copy.\n"
            f"Translate from {source_language or 'the source language'} into {target_language}.\n"
            "Preserve meaning, story facts, names, worldview, plot, tone, point of view, tense, "
            "paragraph order and block roles. Use an established target-language form for a proper "
            "name only when one exists. Do not localize culture, customs, setting, food, clothing, "
            "housing, transport, institutions or plot. Do not add, omit, summarize, explain or censor.\n"
            "Return JSON only, with exactly the same title keys, block count, block order and block "
            'types: {"titles":{"key":"translated"},"blocks":[{"type":"unchanged","text":"translated"}]}.\n'
            f"SOURCE:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def _parse(text: str, *, original: TranslationUnit) -> TranslationUnit:
        try:
            payload = _TranslationPayload.model_validate(repair_json(text))
        except Exception as error:
            raise TranslationError("translator returned invalid structured content") from error
        if set(payload.titles) != set(original.titles):
            raise TranslationError("translator changed the title contract")
        if len(payload.blocks) != len(original.blocks):
            raise TranslationError("translator changed the block count")
        original_types = [str(block.get("type") or "") for block in original.blocks]
        translated_types = [block.type for block in payload.blocks]
        if translated_types != original_types:
            raise TranslationError("translator changed the block structure")
        return TranslationUnit(
            titles=payload.titles,
            blocks=tuple(
                {**original.blocks[index], "text": block.text}
                for index, block in enumerate(payload.blocks)
            ),
        )
