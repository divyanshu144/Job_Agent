from __future__ import annotations

from sqlalchemy import select

from backend.models import JobResult
from backend.services.job_result import upsert_job_result
from tests.factories import make_analysis


async def _rows(session, analysis_id, agent):
    return (
        (
            await session.execute(
                select(JobResult).where(
                    JobResult.analysis_id == analysis_id,
                    JobResult.agent_name == agent,
                )
            )
        )
        .scalars()
        .all()
    )


async def test_upsert_keeps_one_row_and_increments_retry_count(session):
    analysis = await make_analysis(session)
    await session.commit()

    await upsert_job_result(session, analysis.id, "job_parser", output_json='{"x": 1}')
    await upsert_job_result(
        session, analysis.id, "job_parser", error="boom", error_code="agent_failed"
    )
    await upsert_job_result(session, analysis.id, "job_parser", output_json='{"x": 2}')

    rows = await _rows(session, analysis.id, "job_parser")
    assert len(rows) == 1
    assert rows[0].output_json == '{"x": 2}'
    assert rows[0].error is None
    assert rows[0].error_code is None
    assert rows[0].retry_count == 2  # writes were 0, 1, 2


async def test_upsert_dedups_legacy_error_plus_output_pair(session):
    analysis = await make_analysis(session)
    session.add(JobResult(analysis_id=analysis.id, agent_name="resume_tailorer", error="old"))
    session.add(
        JobResult(analysis_id=analysis.id, agent_name="resume_tailorer", output_json='{"a": 1}')
    )
    await session.flush()

    await upsert_job_result(session, analysis.id, "resume_tailorer", output_json='{"a": 2}')

    rows = await _rows(session, analysis.id, "resume_tailorer")
    assert len(rows) == 1
    assert rows[0].output_json == '{"a": 2}'
