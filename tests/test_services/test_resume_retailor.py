from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import backend.models  # noqa: F401
from backend.models import JobResult
from backend.schemas import ResumeTailorerOutput
from backend.services import resume_document as docsvc
from backend.services.resume_retailor import retailor_analysis
from tests.factories import make_analysis, make_profile, make_user


async def test_retailor_applies_via_cas_and_preserves_history(db_session):
    user = await make_user(db_session)
    await make_profile(
        db_session,
        user_id=user.id,
        profile_review_data="{}",
        yaml_data="Python",
        merged_profile="m",
    )
    analysis = await make_analysis(db_session, user_id=user.id)
    db_session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="job_parser",
            output_json=json.dumps(
                {
                    "required_skills": ["Python"],
                    "nice_to_have": [],
                    "role_type": "BE",
                    "seniority": "Senior",
                }
            ),
        )
    )
    await db_session.flush()
    fork = await docsvc.ensure_analysis_resume(
        db_session, user.id, analysis.id, json.dumps({"headline": "old tailoring"})
    )
    new_output = ResumeTailorerOutput(headline="re-tailored from new master")
    with patch(
        "backend.agents.resume_tailorer.ResumeTailorerAgent.run",
        new_callable=AsyncMock,
        return_value=new_output,
    ):
        doc = await retailor_analysis(db_session, user.id, analysis, fork, base_rev=0)
    assert doc.rev == 1  # applied as a CAS write — old tailoring is one undo away
    assert json.loads(doc.content_json)["headline"] == "re-tailored from new master"
