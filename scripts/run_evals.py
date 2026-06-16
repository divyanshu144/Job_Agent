#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from backend.evals.dataset import DEFAULT_FIXTURE_PATH
    from backend.evals.runner import run_deterministic_eval

    parser = argparse.ArgumentParser(description="Run JobFit deterministic eval fixtures.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--report", default="reports/evals/latest.json")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Reserved for live Anthropic evals; requires RUN_LIVE_EVALS=1.",
    )
    args = parser.parse_args()

    if args.live and os.getenv("RUN_LIVE_EVALS") != "1":
        print("Skipping live evals: set RUN_LIVE_EVALS=1 to enable Anthropic calls.")
        return 0
    if args.live:
        print("Live eval runner is not implemented yet; no Anthropic calls were made.")
        return 0

    run = run_deterministic_eval(args.fixtures, report_path=Path(args.report))
    print(
        f"Deterministic evals: {run.total_cases - run.failed_cases}/"
        f"{run.total_cases} cases passed"
    )
    print(f"Report: {args.report}")
    for case in run.cases:
        if not case.passed:
            print(f"\n{case.case_id}")
            for failure in case.failures:
                print(f"  - {failure}")
    return 0 if run.passed else 1


if __name__ == "__main__":
    sys.exit(main())
