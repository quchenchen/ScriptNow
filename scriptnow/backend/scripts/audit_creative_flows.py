from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from scriptnow.platform.creative_flow_audit import audit_flow, load_observation, load_scenario


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit ScriptNow creative-flow evidence against a golden scenario."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = audit_flow(load_scenario(args.scenario), load_observation(args.observation))
    except (OSError, ValidationError) as exc:
        parser.error(str(exc))

    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{payload}\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
