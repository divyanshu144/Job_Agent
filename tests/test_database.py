import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models import Analysis, JobResult, Profile


@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


async def test_tables_created(engine):
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result}
    assert "profiles" in tables
    assert "analyses" in tables
    assert "job_results" in tables


async def test_profile_insert(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        p = Profile(yaml_data="name: test", cv_text="", github_data="{}", merged_profile="test")
        session.add(p)
        await session.commit()
        await session.refresh(p)
        assert p.id is not None
        assert p.last_refreshed_at is not None


async def test_analysis_with_results(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        p = Profile(yaml_data="x", cv_text="", github_data="{}", merged_profile="x")
        session.add(p)
        await session.flush()
        a = Analysis(jd_text="Senior ML Engineer", profile_id=p.id)
        session.add(a)
        await session.flush()
        r = JobResult(analysis_id=a.id, agent_name="job_parser", output_json='{"skills": []}')
        session.add(r)
        await session.commit()
        assert r.id is not None


@pytest.mark.asyncio
async def test_llm_call_has_cache_token_columns(engine):
    """LLMCall model accepts and stores cache_creation_tokens and cache_read_tokens."""
    from datetime import datetime, timezone

    from backend.models import LLMCall

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        row = LLMCall(
            agent_name="test_agent",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.0001,
            latency_ms=500,
            cache_hit=False,
            cache_creation_tokens=800,
            cache_read_tokens=0,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()

        result = await session.get(LLMCall, row.id)
        assert result.cache_creation_tokens == 800
        assert result.cache_read_tokens == 0
