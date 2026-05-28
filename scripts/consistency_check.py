#!/usr/bin/env python3
"""
Standalone consistency checker for match_scorer.

Usage:
    python scripts/consistency_check.py --jd-file path/to/jd.txt
    python scripts/consistency_check.py --jd-file path/to/jd.txt --runs 5

Exit codes:
    0  — variance within threshold (≤ 15)
    1  — variance exceeds threshold
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _jaccard_overlap(a: list[str], b: list[str]) -> float:
    sa = {s.lower() for s in a}
    sb = {s.lower() for s in b}
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


async def _run(jd: str, runs: int) -> int:
    from backend.agents.match_scorer import MatchScorerAgent
    from backend.schemas import MatchScorerOutput, PriorOutputs

    agent = MatchScorerAgent()
    prior = PriorOutputs()
    results: list[MatchScorerOutput] = []

    print(f"Running match_scorer {runs} time(s)…")
    for i in range(runs):
        out = await agent.run("", jd, prior)
        results.append(out)
        print(f"  Run {i + 1}: score={out.score}")

    scores = [r.score for r in results]
    variance = max(scores) - min(scores) if len(scores) > 1 else 0

    pairs = [(i, j) for i in range(runs) for j in range(i + 1, runs)]
    matched_overlaps = [
        _jaccard_overlap(results[i].matched_skills, results[j].matched_skills)
        for i, j in pairs
    ]
    missing_overlaps = [
        _jaccard_overlap(results[i].missing_skills, results[j].missing_skills)
        for i, j in pairs
    ]
    avg_matched = sum(matched_overlaps) / len(matched_overlaps) if matched_overlaps else 1.0
    avg_missing = sum(missing_overlaps) / len(missing_overlaps) if missing_overlaps else 1.0

    print("\n=== Consistency Report ===")
    print(f"  Scores:               {scores}")
    print(
        f"  Variance (max-min):   {variance}"
        f"  {'✓' if variance <= 15 else '✗ EXCEEDS threshold of 15'}"
    )
    print(f"  matched_skills overlap: {avg_matched:.0%}  {'✓' if avg_matched >= 0.70 else '✗'}")
    print(f"  missing_skills overlap: {avg_missing:.0%}  {'✓' if avg_missing >= 0.70 else '✗'}")

    return 0 if variance <= 15 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check match_scorer consistency across N runs."
    )
    parser.add_argument(
        "--jd-file", required=True, help="Path to a plain-text job description file"
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of runs (default: 3)")
    args = parser.parse_args()

    jd = Path(args.jd_file).read_text()
    exit_code = asyncio.run(_run(jd, args.runs))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
