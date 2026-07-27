from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from scriptnow.platform.skill_benchmarks import (
    SkillBenchmarkError,
    SkillTrialResult,
    evaluate_skill_trials,
    load_benchmark_suite,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate paired baseline and candidate Skill trial evidence."
    )
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--trials", required=True, type=Path)
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        suite = load_benchmark_suite(args.suite)
        raw_trials = json.loads(args.trials.read_text(encoding="utf-8"))
        trials = TypeAdapter(list[SkillTrialResult]).validate_python(raw_trials)
        report = evaluate_skill_trials(
            suite=suite,
            candidate_skill_digest=args.candidate_digest,
            trials=trials,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        SkillBenchmarkError,
    ) as error:
        raise SystemExit(f"benchmark evidence is invalid: {error}") from error

    rendered = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
