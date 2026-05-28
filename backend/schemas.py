from __future__ import annotations

from datetime import datetime

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


class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None = None
    role_type: str
    seniority: str
    company: str | None = None


class MatchScorerOutput(BaseModel):
    score: int = Field(..., ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    partial_matches: list[str]


class GapAnalystOutput(BaseModel):
    critical_gaps: list[GapItem]
    nice_to_have_gaps: list[GapItem]


class ResourcePlannerOutput(BaseModel):
    gaps: list[ResourceItem]


class CoverLetterOutput(BaseModel):
    subject: str
    body: str
    tone_notes: str


class ResumeTailorerOutput(BaseModel):
    tailored_bullets: list[BulletItem]


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
    github_data: str
    merged_profile: str
    last_refreshed_at: datetime
    github_last_fetched_at: datetime | None = None
    warnings: list[str] = []


class ProfileStatusResponse(BaseModel):
    profile_last_built_at: datetime
    github_last_fetched_at: datetime | None
    github_is_stale: bool
    github_stale_after_days: int


class GitHubRefreshResponse(BaseModel):
    repos_updated: int
    github_last_fetched_at: datetime
    profile: ProfileResponse


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
