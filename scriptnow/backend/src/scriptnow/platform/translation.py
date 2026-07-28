import json
from contextlib import suppress

from json_repair import loads as repair_json
from pydantic import BaseModel, ConfigDict

from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectRunModel, RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.translation_contracts import TranslationError, TranslationUnit


class _TranslationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titles: tuple[str, ...]
    blocks: tuple[str, ...]


class FaithfulTranslationService:
    """Translate export-only content without changing adopted domain revisions."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.runs = RunCoordinator(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
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
        glossary_block: str = "",
        run_id: str | None = None,
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
        manages_run = run_id is None
        if manages_run:
            run = await self.runs.enqueue(
                tenant_id=tenant_id,
                project_id=project_id,
                idempotency_key=f"faithful-translation:{idempotency_key}",
            )
        else:
            async with self.database.session() as session:
                record = await session.get(ProjectRunModel, run_id)
            run = record
        if run is None or (
            not manages_run
            and (run.tenant_id != tenant_id or run.project_id != project_id)
        ):
            raise TranslationError("translation run is outside project scope")
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
        if manages_run:
            await self.runs.transition(
                tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING
            )
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
                        glossary_block=glossary_block,
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
            if manages_run:
                await self.runs.transition(
                    tenant_id=tenant_id, run_id=run.id, target=RunStatus.SUCCEEDED
                )
            return tuple(translated)
        except Exception as error:
            with suppress(Exception):
                await self.billing.release(reservation.id)
            if manages_run:
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
        *, source_language: str, target_language: str, unit: TranslationUnit,
        glossary_block: str = "",
    ) -> str:
        payload = {
            "titles": list(unit.titles.values()),
            "blocks": [str(block.get("text", "")) for block in unit.blocks],
        }
        glossary_section = f"\n{glossary_block}\n" if glossary_block else ""
        return (
            "You are performing faithful literary translation for an export copy.\n"
            f"Translate from {source_language or 'the source language'} into {target_language}.\n"
            f"{glossary_section}"
            "Preserve meaning, story facts, names, worldview, plot, tone, point of view, tense, "
            "paragraph order and block roles. Use an established target-language form for a proper "
            "name only when one exists. Do not localize culture, customs, setting, food, clothing, "
            "housing, transport, institutions or plot. Do not add, omit, summarize, explain or censor.\n"
            "The server owns all keys, IDs, block types and metadata. Translate only the ordered "
            "text values supplied below; never return or alter structural metadata. Return JSON only "
            'with the same array lengths and order: {"titles":["translated"],"blocks":["translated"]}.\n'
            f"SOURCE:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def _parse(text: str, *, original: TranslationUnit) -> TranslationUnit:
        try:
            payload = _TranslationPayload.model_validate(repair_json(text))
        except Exception as error:
            raise TranslationError(
                "translator returned an invalid structured response"
            ) from error
        if len(payload.titles) != len(original.titles):
            raise TranslationError("translator changed the title count")
        if len(payload.blocks) != len(original.blocks):
            raise TranslationError("translator changed the block count")
        return TranslationUnit(
            titles=dict(zip(original.titles, payload.titles, strict=True)),
            blocks=tuple(
                {**original.blocks[index], "text": text}
                for index, text in enumerate(payload.blocks)
            ),
        )
