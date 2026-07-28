from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scriptnow.diagnostics.real_provider_replay import (
    RealProviderReplayError,
    replay_persisted_four_domain_flows,
)
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit four persisted domain flows that were executed with a real Provider. "
            "The report contains opaque references and no project content or credentials."
        )
    )
    parser.add_argument("--database-url", default=Settings().database_url)
    parser.add_argument("--novel-project", required=True)
    parser.add_argument("--script-project", required=True)
    parser.add_argument("--translation-project", required=True)
    parser.add_argument("--recreation-project", required=True)
    parser.add_argument(
        "--golden-root",
        type=Path,
        default=Path(__file__).parents[1] / "golden" / "creative-flow-v1",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    database = Database.create(args.database_url)
    try:
        async with database.session() as session:
            report = await replay_persisted_four_domain_flows(
                session,
                golden_root=args.golden_root,
                project_ids={
                    "novel": args.novel_project,
                    "script": args.script_project,
                    "translation": args.translation_project,
                    "recreation": args.recreation_project,
                },
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{report.model_dump_json(indent=2)}\n", encoding="utf-8")
        return 0 if report.passed else 2
    finally:
        await database.dispose()


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except RealProviderReplayError as error:
        raise SystemExit(f"real Provider replay rejected: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
