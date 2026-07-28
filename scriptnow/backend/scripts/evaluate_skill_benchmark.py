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
    record_skill_admission,
)
from scriptnow.platform.skills import SkillCatalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate paired baseline and candidate Skill trial evidence."
    )
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--trials", required=True, type=Path)
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--domain")
    parser.add_argument("--skill")
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
        admission_args = [args.skills_root, args.admission, args.domain, args.skill]
        if any(admission_args) and not all(admission_args):
            raise SkillBenchmarkError(
                "admission update requires --skills-root, --admission, --domain and --skill"
            )
        if all(admission_args):
            descriptor = next(
                (
                    item
                    for item in SkillCatalog(args.skills_root).scan()
                    if item.domain == args.domain and item.name == args.skill
                ),
                None,
            )
            if descriptor is None:
                raise SkillBenchmarkError(
                    f"candidate skill does not exist: {args.domain}/{args.skill}"
                )
            if descriptor.digest != args.candidate_digest:
                raise SkillBenchmarkError(
                    "candidate digest does not match the current Skill contents"
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
    if all([args.skills_root, args.admission, args.domain, args.skill]):
        if args.output is None:
            raise SystemExit("--output is required when updating admission")
        record_skill_admission(
            registry_path=args.admission,
            domain=args.domain,
            skill_name=args.skill,
            report=report,
            report_path=str(args.output),
        )
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
