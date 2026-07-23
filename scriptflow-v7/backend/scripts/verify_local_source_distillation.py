"""Exercise the complete source-distillation state machine without external model calls."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import func, select

from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import RagChunkModel, SourceProfileModel
from scriptflow_v7.platform.source_distillation import SourceDistillationService
from scriptflow_v7.platform.source_distillation_runner import SourceDistillationRunner


class LocalContractAnalyzer:
    """Produces citation-safe structural markers; it does not evaluate manuscript quality."""

    async def analyze(
        self, *, pass_key: str, payload: dict[str, object]
    ) -> dict[str, object]:
        if pass_key == "atomic_evidence":
            return {
                "evidence": [
                    {
                        "evidence_key": f"local-atomic-{chunk['chunk_id']}",
                        "chunk_id": chunk["chunk_id"],
                        "source_unit": f"indexed-unit-{chunk['ordinal']}",
                        "dimension": "quality_risk",
                        "claim": "The indexed source unit is available for a later model-backed pass.",
                        "confidence": 100,
                    }
                    for chunk in payload["chunks"]
                ]
            }
        if pass_key == "cross_unit_synthesis":
            first = payload["evidence"][0]
            group = int(payload["group"])
            return {
                "evidence": [
                    {
                        "evidence_key": f"local-synthesis-{group}",
                        "chunk_id": first["chunk_id"],
                        "source_unit": f"local-batch-{group}",
                        "dimension": "quality_risk",
                        "claim": "This batch passed citation and checkpoint validation.",
                        "confidence": 100,
                        "inference": True,
                        "related_evidence_keys": [first["evidence_key"]],
                    }
                ]
            }
        if pass_key == "conflict_gap_check":
            return {
                "conflicts": [],
                "gaps": ["Creative interpretation requires the authorized model-backed pass."],
                "dimension_coverage": {"quality_risk": len(payload["evidence"])},
            }
        if pass_key == "candidate_profile":
            return {
                "profile": {
                    "verification_only": True,
                    "result": "The local source pipeline completed; no creative claims were made.",
                },
                "evidence_keys": [item["evidence_key"] for item in payload["evidence"]],
                "exclusions": ["creative use", "author imitation", "automatic approval"],
                "ready_with_gaps": True,
            }
        raise RuntimeError(f"unsupported verification pass: {pass_key}")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--source-file-id", action="append", required=True)
    parser.add_argument("--key", default="")
    return parser.parse_args()


async def main() -> None:
    args = arguments()
    database = Database.create(Settings().database_url)
    service = SourceDistillationService(database)
    key = args.key.strip() or f"local-contract-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    before = await service.approved_profile(tenant_id=args.tenant_id, project_id=args.project_id)
    run = await service.start(
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        source_file_ids=args.source_file_id,
        idempotency_key=key,
    )
    result = await SourceDistillationRunner(
        database,
        LocalContractAnalyzer(),
        chunk_batch_size=20,
        evidence_batch_size=100,
    ).run(tenant_id=args.tenant_id, distillation_id=run.id)
    async with database.session() as session:
        expected_chunks = int(
            await session.scalar(
                select(func.count(RagChunkModel.id)).where(
                    RagChunkModel.tenant_id == args.tenant_id,
                    RagChunkModel.project_id == args.project_id,
                    RagChunkModel.source_file_id.in_(args.source_file_id),
                )
            )
            or 0
        )
        candidate = await session.get(SourceProfileModel, result.profile_id)
    if candidate is None or result.processed_chunks != expected_chunks:
        raise RuntimeError("local contract verification did not cover every indexed chunk")
    await service.decide(
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        profile_id=candidate.id,
        approve=False,
        feedback="Local contract verification only; contains no model-backed creative analysis.",
    )
    after = await service.approved_profile(tenant_id=args.tenant_id, project_id=args.project_id)
    if (before.id if before else None) != (after.id if after else None):
        raise RuntimeError("verification candidate changed the approved source profile")
    print(
        json.dumps(
            {
                **asdict(result),
                "expected_chunks": expected_chunks,
                "decision": "rejected_verification_only",
                "approved_profile_unchanged": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
