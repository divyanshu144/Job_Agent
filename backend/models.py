from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    yaml_data: Mapped[str] = mapped_column(Text)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    merged_profile: Mapped[str] = mapped_column(Text, default="")
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, default=None
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class InviteToken(Base):
    __tablename__ = "invite_tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    used_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, default=None
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    agent_name: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    analysis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("analyses.id"), nullable=True, default=None
    )
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("discovery_runs.id"), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PipelineEvent(Base):
    """Structured observability event (span | failure | tool | retry) for one pipeline run.

    Correlated by trace_id (a fresh uuid per entry point); also carries the domain
    keys analysis_id / run_id (nullable) so events join back to LLMCall cost rows.
    """

    __tablename__ = "pipeline_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    trace_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # span | failure | tool | retry
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ok")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)  # JSON
    analysis_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    __table_args__ = (Index("ix_pipeline_events_trace_kind", "trace_id", "kind"),)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String)
    triggered_by: Mapped[str] = mapped_column(String, default="manual")
    status: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_passed_stage1: Mapped[int] = mapped_column(Integer, default=0)
    jobs_passed_stage2: Mapped[int] = mapped_column(Integer, default=0)
    jobs_scored: Mapped[int] = mapped_column(Integer, default=0)
    # JSON: {source: {status, jobs_found, jobs_scored, error}} — populated for "all" runs
    source_statuses: Mapped[str] = mapped_column(Text, default="{}")
    jobs: Mapped[list[Job]] = relationship("Job", back_populates="run")
    batches: Mapped[list[DiscoveryBatch]] = relationship("DiscoveryBatch", back_populates="run")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    sources: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of source names
    source_id: Mapped[str] = mapped_column(String, default="")
    source_url: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    company: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    raw_text: Mapped[str] = mapped_column(Text)  # required, no default
    dedup_hash: Mapped[str] = mapped_column(String, unique=True, index=True)  # required, no default
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    state: Mapped[str] = mapped_column(String, default="discovered", index=True)
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    matched_profiles: Mapped[str] = mapped_column(Text, default="[]")
    discovery_run_id: Mapped[str] = mapped_column(String, ForeignKey("discovery_runs.id"))
    run: Mapped[DiscoveryRun] = relationship("DiscoveryRun", back_populates="jobs")


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    jd_text: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluate_only: Mapped[bool] = mapped_column(Boolean, default=False)
    jd_hash: Mapped[str] = mapped_column(String, default="", index=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # Denormalized from job_parser/match_scorer outputs for the History list (and
    # future application-tracker sort/filter). Populated at write time + backfill.
    role_type: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    company: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    # Per-run quality summary (JSON), populated at end of Phase 2 (see orchestrator).
    quality_signals: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    job_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("jobs.id"), nullable=True, default=None
    )
    user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, default=None
    )
    results: Mapped[list[JobResult]] = relationship("JobResult", back_populates="analysis")
    contacts: Mapped[list[Contact]] = relationship("Contact", back_populates="analysis")


class JobResult(Base):
    __tablename__ = "job_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"))
    agent_name: Mapped[str] = mapped_column(String)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="results")


class Feedback(Base):
    """User rating of a generated analysis/agent output.

    Capture-only for now; a future evals scorer (backend/evals/) consumes these.
    """

    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), index=True)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    rating: Mapped[int] = mapped_column(Integer)  # e.g. -1 / +1, or 1–5
    note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"), index=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    title: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    company: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String, default="hunter")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="discovered")
    draft_subject: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="contacts")


class DiscoveryBatch(Base):
    """Tracks a single Anthropic Batch API submission for a discovery run's Stage 2 phase."""

    __tablename__ = "discovery_batches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("discovery_runs.id"), index=True)
    anthropic_batch_id: Mapped[str] = mapped_column(String)  # "msgbatch_01..."
    status: Mapped[str] = mapped_column(String, default="submitted")  # submitted | ended | failed
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    run: Mapped[DiscoveryRun] = relationship("DiscoveryRun", back_populates="batches")
