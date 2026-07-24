"""Run the resumable source-distillation loop for a real novel project."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime

from scriptnow.platform.agent_factory import AgentFactory
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeResult
from scriptnow.platform.audit import AuditService
from scriptnow.platform.billing import BillingError, BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import RunStatus, TenantModel
from scriptnow.platform.run_coordinator import RunCoordinator, RunTransitionError
from scriptnow.platform.source_distillation import SourceDistillationService
from scriptnow.platform.source_distillation_runner import (
    AgentRuntimeDistillationAnalyzer,
    SourceDistillationRunner,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--source-file-id", action="append", required=True)
    parser.add_argument("--key", default="")
    parser.add_argument("--run-key", default="")
    parser.add_argument("--chunk-batch-size", type=int, default=12)
    parser.add_argument("--evidence-batch-size", type=int, default=50)
    parser.add_argument("--max-tokens", type=int, default=250_000)
    parser.add_argument(
        "--allow-external-processing",
        action="store_true",
        help="Authorize sending source chunks to the configured third-party model Provider.",
    )
    return parser.parse_args()


async def main() -> None:
    args = arguments()
    if not args.allow_external_processing:
        raise SystemExit(
            "External processing consent is required. Review the configured Provider and rerun "
            "with --allow-external-processing."
        )
    settings = Settings()
    database = Database.create(settings.database_url)
    await database.create_schema()
    key = args.key.strip() or f"source-distillation-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    run_key = args.run_key.strip() or (
        f"{key}:agent-runtime:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    )
    service = SourceDistillationService(database)
    coordinator = RunCoordinator(database)
    billing = BillingService(database, enforce_limits=settings.environment == "production")
    audit = AuditService(database)
    project_run = None
    reservation = None
    try:
        distillation = await service.start(
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            source_file_ids=args.source_file_id,
            idempotency_key=key,
        )
        project_run = await coordinator.enqueue(
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            idempotency_key=run_key,
        )
        if project_run.status == RunStatus.QUEUED:
            await coordinator.transition(
                tenant_id=args.tenant_id,
                run_id=project_run.id,
                target=RunStatus.RUNNING,
            )
        async with database.session() as session:
            tenant = await session.get(TenantModel, args.tenant_id)
            if tenant is None:
                raise RuntimeError("tenant does not exist")
        reservation = await billing.reserve(
            tenant_id=args.tenant_id,
            run_id=project_run.id,
            idempotency_key=f"source-distillation:{run_key}",
            tier=tenant.tier,
            max_tokens=args.max_tokens,
            ttl_minutes=120,
        )
        runtime_snapshot = await AgentFactory(database).snapshot_for_run(
            tenant_id=args.tenant_id,
            run_id=project_run.id,
            role_key="reviewer",
            stage_override="source-analysis",
            explicit_skill_keys=("novel-source-distiller",),
        )
        await audit.record(
            tenant_id=args.tenant_id,
            actor_id="operator-cli",
            action="source_distillation.external_processing_authorized",
            resource_type="source_distillation",
            resource_id=distillation.id,
            outcome="succeeded",
            correlation_id=project_run.id,
            details={
                "consent_version": "source-processing-v1",
                "provider_key": runtime_snapshot.values.get("provider_key"),
                "model_key": runtime_snapshot.values.get("model_key"),
                "source_file_ids": distillation.source_file_ids,
            },
        )

        async def record_usage(pass_key: str, call_index: int, result: AgentRuntimeResult) -> None:
            await billing.record_model_call(
                reservation_id=reservation.id,
                tenant_id=args.tenant_id,
                run_id=project_run.id,
                framework_event_id=f"source-distillation:{pass_key}:{call_index}",
                trace_id=project_run.id,
                agent_role="reviewer",
                model_key=result.model_key,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                input_price_per_million=result.input_price_per_million,
                output_price_per_million=result.output_price_per_million,
            )

        runner = SourceDistillationRunner(
            database,
            AgentRuntimeDistillationAnalyzer(
                AgentRuntime(database, settings),
                tenant_id=args.tenant_id,
                run_id=project_run.id,
                usage_sink=record_usage,
            ),
            chunk_batch_size=args.chunk_batch_size,
            evidence_batch_size=args.evidence_batch_size,
        )
        result = await runner.run(
            tenant_id=args.tenant_id,
            distillation_id=distillation.id,
        )
        if project_run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            await coordinator.transition(
                tenant_id=args.tenant_id,
                run_id=project_run.id,
                target=RunStatus.WAITING,
                waiting_reason="source_profile_decision",
            )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    except Exception:
        if project_run is not None:
            with suppress(RunTransitionError):
                await coordinator.transition(
                    tenant_id=args.tenant_id,
                    run_id=project_run.id,
                    target=RunStatus.FAILED,
                    error_code="source_distillation_failed",
                )
        raise
    finally:
        if reservation is not None:
            with suppress(BillingError):
                await billing.finalize(reservation.id)
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
