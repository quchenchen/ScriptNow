from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scriptnow.diagnostics.creative_flow_evidence import collect_persisted_evidence
from scriptnow.platform.config import Settings
from scriptnow.platform.creative_flow_audit import load_scenario
from scriptnow.platform.database import Database


async def _collect(
    *,
    database_url: str,
    scenario_path: Path,
    project_id: str,
    output_path: Path,
) -> None:
    database = Database.create(database_url)
    try:
        async with database.session() as session:
            observation = await collect_persisted_evidence(
                session,
                scenario=load_scenario(scenario_path),
                project_id=project_id,
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            observation.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect persisted ScriptNow evidence without synthesizing success events."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database-url", default=Settings().database_url)
    args = parser.parse_args()
    asyncio.run(
        _collect(
            database_url=args.database_url,
            scenario_path=args.scenario,
            project_id=args.project_id,
            output_path=args.output,
        )
    )


if __name__ == "__main__":
    main()
