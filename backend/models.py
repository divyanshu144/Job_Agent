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
    UniqueConstraint,
    text,
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
    profile_review_data: Mapped[str] = mapped_column(Text, default="{}")
    review_status: Mapped[str] = mapped_column(String, default="draft")
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InviteToken(Base):
    __tablename__ = "invite_tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    used_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, default=None
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    prompt_name: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    prompt_hash: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    context_chars: Mapped[int] = mapped_column(Integer, default=0)
    analysis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("analyses.id"), nullable=True, default=None
    )
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("discovery_runs.id"), nullable=True, default=None
    )
    # Per-user cost attribution (for campaign caps). Nullable: legacy + admin/
    # discovery calls stay null; campaign/interactive calls carry the user.
    user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # user_spend() sums per user per window on every campaign cap check.
    __table_args__ = (Index("ix_llm_calls_user_created", "user_id", "created_at"),)


class UserCampaignSettings(Base):
    """Per-user campaign caps. One row per user (auto-created with defaults on
    first cap check). monthly_cost_cap_usd gates LLM spend; daily_run_cap gates
    runs/day (enforced once CampaignRun exists — plan unit 5)."""

    __tablename__ = "user_campaign_settings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    daily_run_cap: Mapped[int] = mapped_column(Integer, default=5)
    monthly_cost_cap_usd: Mapped[float] = mapped_column(Float, default=10.0)
    campaign_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class UserTargetCompany(Base):
    """A company on a regular user's per-user target list. Replaces the shared
    assets/target_companies.json for the multi-tenant campaign. (ats, slug) feed
    fetch_ats_jobs; unique per (user, ats, slug)."""

    __tablename__ = "user_target_companies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    ats: Mapped[str] = mapped_column(String)  # greenhouse | lever | ashby
    slug: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (UniqueConstraint("user_id", "ats", "slug", name="uq_user_target"),)


class MemoryChunk(Base):
    """Sparse-vector memory chunk derived from a candidate profile version."""

    __tablename__ = "memory_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, index=True, default=None
    )
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"), index=True)
    namespace: Mapped[str] = mapped_column(String, default="/candidate")
    source: Mapped[str] = mapped_column(String)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    sparse_vector_json: Mapped[str] = mapped_column(Text, default="{}")
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (Index("ix_memory_chunks_profile_namespace", "profile_id", "namespace"),)


class CampaignRun(Base):
    """Per-run ledger for the regular-tier (in-app) campaign + the daily_run_cap
    enforcement point. status: running | completed | failed | blocked (cap/
    disabled — zero LLM spend). jobs_drafted = materials generated (analysis +
    score + gaps + cover letter + tailored resume). error is user-safe."""

    __tablename__ = "campaign_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String, default="running")
    jobs_considered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_drafted: Mapped[int] = mapped_column(Integer, default=0)
    jobs_failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # DB-enforced "one running run per user" — the concurrency guard behind
    # enqueue_campaign_run (a SELECT-then-INSERT check alone races).
    __table_args__ = (
        Index(
            "uq_campaign_runs_one_running",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (Index("ix_pipeline_events_trace_kind", "trace_id", "kind"),)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String)
    triggered_by: Mapped[str] = mapped_column(String, default="manual")
    status: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
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
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
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
    # Concurrency claim for retry: a conditional UPDATE sets this to now() when a
    # retry starts and clears it in finally. NULL means no retry in flight.
    retry_running_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
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
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # User-safe error classification (see services/pipeline_errors.py). NULL on success.
    error_code: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # Bumped on every upsert; 0 on first write. One row per (analysis, agent).
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="contacts")


class CampaignJob(Base):
    """One job's journey through the autonomous application campaign.

    Created when a discovery job scores >= the campaign threshold. status:
    queued (awaiting/processing downstream steps) | drafted (outreach drafted) |
    failed (a per-job step raised; see `error`). match_score is 0–1 and nullable
    so a job that errors before scoring still records a failed row.
    """

    __tablename__ = "campaign_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    draft_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String, default="queued")  # queued | drafted | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DiscoveryBatch(Base):
    """Tracks a single Anthropic Batch API submission for a discovery run's Stage 2 phase."""

    __tablename__ = "discovery_batches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("discovery_runs.id"), index=True)
    anthropic_batch_id: Mapped[str] = mapped_column(String)  # "msgbatch_01..."
    status: Mapped[str] = mapped_column(String, default="submitted")  # submitted | ended | failed
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    run: Mapped[DiscoveryRun] = relationship("DiscoveryRun", back_populates="batches")
