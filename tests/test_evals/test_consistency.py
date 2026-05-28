"""
Integration test: run match_scorer N times on the same input and assert
score variance and skill overlap are within acceptable bounds.

Run with:  make eval-consistency
Skip in:   make test   (filtered by -m 'not integration')
"""

from __future__ import annotations

import pytest

from backend.agents.match_scorer import MatchScorerAgent
from backend.schemas import MatchScorerOutput, PriorOutputs

# ---------------------------------------------------------------------------
# Fixed fixtures — realistic 200-word SWE job description
# ---------------------------------------------------------------------------

JD = """
We are looking for a Senior Backend Engineer to join our platform team.
You will design, build, and maintain high-performance APIs and services that
power our core product. The role requires deep expertise in Python and
experience with distributed systems.

Responsibilities:
- Design and implement RESTful APIs using FastAPI or Django REST Framework
- Build and operate services on AWS (ECS, RDS, S3, SQS)
- Work with PostgreSQL and Redis for persistence and caching
- Contribute to CI/CD pipelines using GitHub Actions and Docker
- Collaborate with frontend engineers and product managers
- Participate in on-call rotation and incident response

Requirements:
- 4+ years of backend engineering experience
- Strong Python skills (asyncio, type hints, testing with pytest)
- Experience with SQL databases and query optimisation
- Familiarity with containerisation (Docker, Kubernetes)
- Comfortable with system design and API design patterns
- Experience with message queues (SQS, RabbitMQ, or Kafka) is a plus

We value clear communication, ownership, and iterative delivery.
Remote-friendly within EU time zones.
""".strip()

PROFILE = """
Software engineer, 5 years experience.
Skills: Python, FastAPI, PostgreSQL, Docker, AWS, Redis, pytest, GitHub Actions.
""".strip()


def _jaccard_overlap(a: list[str], b: list[str]) -> float:
    """Fraction of items in the union that appear in both lists (case-insensitive)."""
    sa = {s.lower() for s in a}
    sb = {s.lower() for s in b}
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


@pytest.mark.integration
async def test_match_scorer_consistency() -> None:
    """
    Run match_scorer 3 times on identical input.
    Assert:
      - All runs return valid MatchScorerOutput
      - Score variance (max - min) <= 15
      - matched_skills pairwise Jaccard overlap >= 0.70
      - missing_skills pairwise Jaccard overlap >= 0.70
    """
    agent = MatchScorerAgent()
    prior = PriorOutputs()
    runs: list[MatchScorerOutput] = []

    for i in range(3):
        result = await agent.run(PROFILE, JD, prior)
        assert isinstance(result, MatchScorerOutput), f"Run {i + 1}: expected MatchScorerOutput"
        assert 0 <= result.score <= 100, f"Run {i + 1}: score {result.score} out of range"
        runs.append(result)

    scores = [r.score for r in runs]
    variance = max(scores) - min(scores)

    # Pairwise skill overlaps
    pairs = [(i, j) for i in range(3) for j in range(i + 1, 3)]
    matched_overlaps = [
        _jaccard_overlap(runs[i].matched_skills, runs[j].matched_skills) for i, j in pairs
    ]
    missing_overlaps = [
        _jaccard_overlap(runs[i].missing_skills, runs[j].missing_skills) for i, j in pairs
    ]
    avg_matched = sum(matched_overlaps) / len(matched_overlaps) if matched_overlaps else 1.0
    avg_missing = sum(missing_overlaps) / len(missing_overlaps) if missing_overlaps else 1.0

    # ---- Report ----
    print("\n=== match_scorer consistency report ===")
    for i, r in enumerate(runs, 1):
        print(f"  Run {i}: score={r.score}  matched={r.matched_skills}  missing={r.missing_skills}")
    print(f"  Score variance:         {variance}  (threshold ≤ 15)")
    print(f"  matched_skills overlap: {avg_matched:.0%}  (threshold ≥ 70%)")
    print(f"  missing_skills overlap: {avg_missing:.0%}  (threshold ≥ 70%)")

    # ---- Assertions ----
    assert variance <= 15, f"Score variance too high: {scores} → variance={variance} (max 15)"
    assert avg_matched >= 0.70, f"matched_skills overlap too low: {avg_matched:.0%} (min 70%)"
    assert avg_missing >= 0.70, f"missing_skills overlap too low: {avg_missing:.0%} (min 70%)"
