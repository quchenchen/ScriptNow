"""Evaluate a narrative index against chapter-level retrieval expectations."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.narrative_graph import NarrativeGraphService


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--index-id", required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


async def main() -> None:
    args = arguments()
    cases = json.loads(args.golden.read_text())
    database = Database.create(Settings().database_url)
    service = NarrativeGraphService(database)
    reciprocal_ranks: list[float] = []
    hits = 0
    results: list[dict[str, object]] = []
    try:
        for case in cases:
            retrieved = await service.retrieve(
                tenant_id=args.tenant_id,
                index_id=args.index_id,
                query=case["query"],
                limit=args.limit,
            )
            chapters = [hit.chapter_title for hit in retrieved]
            expected = set(case["expected_chapters"])
            rank = next(
                (index for index, title in enumerate(chapters, start=1) if title in expected),
                None,
            )
            hits += int(rank is not None)
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
            results.append(
                {
                    "id": case["id"],
                    "matched": rank is not None,
                    "rank": rank,
                    "retrieved_chapters": chapters,
                }
            )
        payload = {
            "cases": len(cases),
            f"recall_at_{args.limit}": hits / max(len(cases), 1),
            "mrr": sum(reciprocal_ranks) / max(len(reciprocal_ranks), 1),
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
