from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GapItem(BaseModel):
    skill: str
    impact: str
    rationale: str


class ResourceItem(BaseModel):
    skill: str
    courses: list[str]
    books: list[str]
    projects: list[str]
    estimated_hours: int


class BulletItem(BaseModel):
    original: str
    rewritten: str
    rationale: str


class ValidationWarning(BaseModel):
    """Produced by backend/evals/validators.py after each agent run.
    exclude=True on the field means it is stripped from model_dump() and
    never enters PriorOutputs or downstream prompt context."""

    agent: str
    rule: str
    detail: str
    severity: Literal["warn", "error"]


class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None = None
    role_type: str
    seniority: str
    company: str | None = None
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class MatchScorerOutput(BaseModel):
    score: int = Field(..., ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    partial_matches: list[str]
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class GapAnalystOutput(BaseModel):
    critical_gaps: list[GapItem]
    nice_to_have_gaps: list[GapItem]
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class PlannerMeta(BaseModel):
    """Self-check telemetry from the resource_planner loop (persisted, not a meta-field)."""

    total_llm_calls: int
    retried_gaps: list[str] = Field(default_factory=list)
    low_confidence_gaps: list[str] = Field(default_factory=list)
    gap_confidences: dict[str, float] = Field(default_factory=dict)


class ResourcePlannerOutput(BaseModel):
    gaps: list[ResourceItem]
    planner_meta: PlannerMeta | None = None
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class CoverLetterOutput(BaseModel):
    subject: str
    body: str
    tone_notes: str
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class ResumeTailorerOutput(BaseModel):
    tailored_bullets: list[BulletItem]
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class PriorOutputs(BaseModel):
    job_parser: JobParserOutput | None = None
    match_scorer: MatchScorerOutput | None = None
    gap_analyst: GapAnalystOutput | None = None
    resource_planner: ResourcePlannerOutput | None = None
    cover_letter: CoverLetterOutput | None = None
    resume_tailorer: ResumeTailorerOutput | None = None


class AnalyseRequest(BaseModel):
    jd: str = Field(..., min_length=50, description="Full job description text")


_VALID_STATUSES = {"applied", "interviewing", "rejected", "offer"}


class UpdateStatusRequest(BaseModel):
    status: str | None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)} or null")
        return v


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    yaml_data: str
    cv_text: str
    merged_profile: str
    last_refreshed_at: datetime
    warnings: list[str] = []


class PipelineDoneData(BaseModel):
    analysis_id: str
    score: int
    partial: bool
    evaluate_only: bool


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool
    status: str | None = None
    role_type: str | None = None
    company: str | None = None
    match_score: int | None = None


class AnalysisDetail(BaseModel):
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool
    status: str | None = None
    results: dict[str, dict]  # type: ignore[type-arg]


class FunnelMetrics(BaseModel):
    jobs_found: int
    passed_stage1: int
    passed_stage2: int
    scored: int


class SourceStatusItem(BaseModel):
    """Per-source progress entry inside DiscoveryRunResponse.source_statuses."""

    status: str  # pending | running | done | failed
    jobs_found: int = 0
    jobs_scored: int = 0
    error: str | None = None


class DiscoveryRunResponse(BaseModel):
    id: str
    source: str
    triggered_by: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    funnel: FunnelMetrics
    # Empty dict for single-source runs; populated for "all" runs.
    source_statuses: dict[str, SourceStatusItem] = {}


class DiscoverySourcesResponse(BaseModel):
    """Which sources are configured (credentials present). Values are never exposed."""

    sources: dict[str, bool]


class DiscoveryFeedItem(BaseModel):
    id: str
    title: str
    company: str
    location: str | None
    source_url: str
    sources: list[str]
    relevance_score: int
    matched_profiles: list[str]
    analysis_id: str | None
    state: str
    discovered_at: datetime
    saved: bool = False


class DiscoveryFeedResponse(BaseModel):
    items: list[DiscoveryFeedItem]
    total: int
    has_more: bool


class UserCreate(BaseModel):
    email: str
    password: str
    invite_token: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    is_admin: bool
    created_at: datetime


class InviteCreate(BaseModel):
    email: str | None = None  # if set, only this email can use the invite


class InviteResponse(BaseModel):
    invite_url: str
    token: str
    expires_at: datetime


class AgentCost(BaseModel):
    agent_name: str
    calls: int
    cost_usd: float
    avg_latency_ms: int


class RunCost(BaseModel):
    id: str
    type: str  # "discovery" or "analysis"
    created_at: datetime
    total_cost_usd: float
    total_calls: int
    cached_calls: int
    latency_p50_ms: int
    agents: list[AgentCost]


class CostSummary(BaseModel):
    total_cost_usd: float
    total_calls: int
    real_calls: int
    cached_calls: int
    cache_hit_rate: float
    total_input_tokens: int
    total_output_tokens: int
    # Model tiering: what Haiku calls would have cost at Sonnet rates
    haiku_cost_usd: float = 0.0
    counterfactual_sonnet_cost_usd: float = 0.0
    tiering_savings_usd: float = 0.0
    tiering_ratio: float = 1.0  # counterfactual / actual; 1.0 when no Haiku calls
    # Anthropic prompt caching: tokens served from cache vs baseline cost
    prompt_cache_read_tokens: int = 0
    prompt_cache_creation_tokens: int = 0
    prompt_cache_savings_usd: float = 0.0  # net: read savings minus write overhead


class ColdEmailOutput(BaseModel):
    subject: str
    body: str


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    analysis_id: str
    email: str
    name: str | None
    title: str | None
    company: str | None
    source: str
    confidence: float
    status: str
    draft_subject: str | None
    draft_text: str | None
    sent_at: datetime | None
    created_at: datetime


class DiscoverRequest(BaseModel):
    analysis_id: str
    domain: str | None = None


class DraftResponse(BaseModel):
    subject: str
    body: str


class SendResponse(BaseModel):
    sent: bool


class BatchDiscoveryResponse(BaseModel):
    run_id: str
    mode: str = "batch"
    note: str = (
        "Batch run submitted. Results appear in /discovery/feed when processing completes "
        "(typically 1–60 minutes). Check /discovery/runs/{run_id} for status."
    )


class FeedbackCreate(BaseModel):
    analysis_id: str
    agent_name: str | None = None
    rating: int
    note: str | None = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    analysis_id: str
    agent_name: str | None
    rating: int
    note: str | None
    trace_id: str | None
    created_at: datetime
