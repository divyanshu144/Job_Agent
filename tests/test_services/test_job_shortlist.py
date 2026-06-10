from __future__ import annotations

import json

from backend.models import JobResult
from backend.services.job_shortlist import get_job_shortlist, recommended_action
from tests.factories import make_analysis, make_discovery_run, make_job, make_profile


def test_recommended_action_thresholds():
    assert recommended_action(75) == "apply"
    assert recommended_action(74) == "maybe"
    assert recommended_action(55) == "maybe"
    assert recommended_action(54) == "skip"


async def test_shortlist_sorts_by_score_descending_and_preserves_source_url(db_session):
    profile = await make_profile(db_session)
    run = await make_discovery_run(db_session, source="hn")
    low = await make_job(
        db_session,
        run=run,
        title="Lower",
        company="Acme",
        source_url="https://example.com/low",
        sources='["hn"]',
        state="scored",
        relevance_score=61,
    )
    high = await make_job(
        db_session,
        run=run,
        title="Higher",
        company="Beta",
        source_url="https://example.com/high",
        sources='["reed"]',
        state="scored",
        relevance_score=88,
    )
    await make_analysis(db_session, profile=profile, job_id=low.id)
    await make_analysis(db_session, profile=profile, job_id=high.id)
    await db_session.commit()

    items = await get_job_shortlist(db_session)

    assert [item.id for item in items] == [high.id, low.id]
    assert items[0].source == "reed"
    assert items[0].source_url == "https://example.com/high"
    assert items[0].recommended_action == "apply"
    assert items[1].recommended_action == "maybe"


async def test_shortlist_maps_skip_threshold(db_session):
    profile = await make_profile(db_session)
    run = await make_discovery_run(db_session)
    job = await make_job(
        db_session,
        run=run,
        title="Weak Match",
        company="Acme",
        source_url="https://example.com/weak",
        sources='["hn"]',
        state="scored",
        relevance_score=42,
    )
    await make_analysis(db_session, profile=profile, job_id=job.id)
    await db_session.commit()

    items = await get_job_shortlist(db_session)

    assert len(items) == 1
    assert items[0].recommended_action == "skip"


async def test_shortlist_includes_match_reasons_and_gaps(db_session):
    profile = await make_profile(db_session)
    run = await make_discovery_run(db_session)
    job = await make_job(
        db_session,
        run=run,
        title="Backend Engineer",
        company="Acme",
        source_url="https://example.com/backend",
        sources='["hn"]',
        state="scored",
        relevance_score=82,
    )
    analysis = await make_analysis(db_session, profile=profile, job_id=job.id)
    db_session.add_all(
        [
            JobResult(
                analysis_id=analysis.id,
                agent_name="match_scorer",
                output_json=json.dumps(
                    {
                        "score": 82,
                        "matched_skills": ["Python", "PostgreSQL"],
                        "missing_skills": ["Kubernetes"],
                        "partial_matches": ["Django"],
                    }
                ),
            ),
            JobResult(
                analysis_id=analysis.id,
                agent_name="gap_analyst",
                output_json=json.dumps(
                    {
                        "critical_gaps": [
                            {"skill": "Kubernetes", "impact": "high", "rationale": "required"}
                        ],
                        "nice_to_have_gaps": [],
                    }
                ),
            ),
        ]
    )
    await db_session.commit()

    items = await get_job_shortlist(db_session)

    assert items[0].top_match_reasons == ["Python", "PostgreSQL", "Django"]
    assert items[0].top_gaps == ["Kubernetes"]


async def test_workatastartup_jobs_participate_only_when_enabled(db_session, monkeypatch):
    from backend.services import job_shortlist

    profile = await make_profile(db_session)
    run = await make_discovery_run(db_session, source="workatastartup")
    job = await make_job(
        db_session,
        run=run,
        title="YC Role",
        company="YC Co",
        source_url="https://account.ycombinator.com/apply",
        sources='["workatastartup"]',
        state="scored",
        relevance_score=90,
    )
    await make_analysis(db_session, profile=profile, job_id=job.id)
    await db_session.commit()

    monkeypatch.setattr(job_shortlist.settings, "enable_workatastartup_source", False)
    assert await get_job_shortlist(db_session) == []

    monkeypatch.setattr(job_shortlist.settings, "enable_workatastartup_source", True)
    items = await get_job_shortlist(db_session)
    assert [item.id for item in items] == [job.id]
