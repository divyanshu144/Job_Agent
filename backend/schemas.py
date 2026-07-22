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


class OmittedItem(BaseModel):
    field: str
    value: str
    reason: str


class ResumeExperienceItem(BaseModel):
    company: str | None = None
    role: str | None = None
    dates: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ResumeProjectItem(BaseModel):
    name: str
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ResumeEducationItem(BaseModel):
    institution: str | None = None
    degree: str | None = None
    dates: str | None = None


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
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ResumeExperienceItem] = Field(default_factory=list)
    projects: list[ResumeProjectItem] = Field(default_factory=list)
    education: list[ResumeEducationItem] = Field(default_factory=list)
    tailored_bullets: list[BulletItem] = Field(default_factory=list)
    omitted_items: list[OmittedItem] = Field(default_factory=list)
    validation_warnings: list[ValidationWarning] = Field(default_factory=list, exclude=True)


class ProfileReviewProject(BaseModel):
    name: str = ""
    description: str = ""
    highlights: list[str] = Field(default_factory=list)


class ProfileReviewExperience(BaseModel):
    company: str = ""
    role: str = ""
    dates: str = ""
    highlights: list[str] = Field(default_factory=list)


class ProfileReviewEducation(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    dates: str = ""


class ProfileReviewLink(BaseModel):
    label: str = ""
    url: str = ""


class ResumeIdentity(BaseModel):
    """Per-user header data for a rendered resume — keeps one person's name/contact
    out of every other user's PDF. Built from the user's profile + account email."""

    name: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    links: list[ProfileReviewLink] = Field(default_factory=list)


class ProfileWorkPreferences(BaseModel):
    locations: list[str] = Field(default_factory=list)
    remote: str | None = None
    role_types: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)


class ProfileReviewData(BaseModel):
    target_role: str = ""
    target_roles: list[str] = Field(default_factory=list)
    key_skills: list[str] = Field(default_factory=list)
    projects: list[ProfileReviewProject] = Field(default_factory=list)
    experience: list[ProfileReviewExperience] = Field(default_factory=list)
    education: list[ProfileReviewEducation] = Field(default_factory=list)
    links: list[ProfileReviewLink] = Field(default_factory=list)
    work_preferences: ProfileWorkPreferences = Field(default_factory=ProfileWorkPreferences)


class ExtractedIdentity(BaseModel):
    name: str = ""
    headline: str = ""
    location: str = ""
    phone: str = ""


class ExtractedSkills(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class ExtractedExperience(BaseModel):
    company: str = ""
    role: str = ""
    dates: str = ""
    highlights: list[str] = Field(default_factory=list)


class ExtractedProject(BaseModel):
    name: str = ""
    themes: list[str] = Field(default_factory=list)


class ExtractedEducation(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    dates: str = ""


class ExtractedProfile(BaseModel):
    """Structured candidate profile extracted from resume text by profile_extractor.
    Serialized to YAML (extracted_profile_to_yaml) to populate Profile.yaml_data."""

    identity: ExtractedIdentity = Field(default_factory=ExtractedIdentity)
    core_skills: ExtractedSkills = Field(default_factory=ExtractedSkills)
    experience: list[ExtractedExperience] = Field(default_factory=list)
    featured_projects: list[ExtractedProject] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)


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
    profile_review_data: str = "{}"
    review_status: str = "draft"
    reviewed_at: datetime | None = None
    last_refreshed_at: datetime
    warnings: list[str] = []


class ProfileReviewResponse(BaseModel):
    profile_id: str
    review_data: ProfileReviewData
    review_status: str
    reviewed_at: datetime | None = None
    has_cv_text: bool = False


class ProfileReviewUpdate(BaseModel):
    review_data: ProfileReviewData


class ProfileYamlUpdate(BaseModel):
    yaml_text: str


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
    profile_stale: bool = False


class RetryRequest(BaseModel):
    agents: list[str] | None = None
    scope: Literal["failed", "all"] = "failed"


class Step(BaseModel):
    name: str
    phase: int  # 1 (evaluate) | 2 (generate)
    status: Literal["success", "error", "pending"]
    error_code: str | None = None
    message: str | None = None  # user-safe; never str(exc)


class AnalysisDetail(BaseModel):
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool
    status: str | None = None
    results: dict[str, dict]  # type: ignore[type-arg]
    result_errors: dict[str, str] = Field(default_factory=dict)
    result_contexts: dict[str, dict] = Field(default_factory=dict)  # type: ignore[type-arg]
    steps: list[Step] = Field(default_factory=list)
    profile_stale: bool = False
    current_profile_id: str | None = None


class TargetCompanyCreate(BaseModel):
    name: str = Field(..., min_length=1)
    ats: Literal["greenhouse", "lever", "ashby"]
    slug: str = Field(..., min_length=1)


class TargetCompanyUpdate(BaseModel):
    active: bool


class TargetCompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    ats: str
    slug: str
    active: bool
    created_at: datetime


class CampaignRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    jobs_considered: int
    jobs_drafted: int
    jobs_failed: int
    error: str | None = None


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


class JobShortlistItem(BaseModel):
    id: str
    title: str
    company: str
    location: str | None
    source: str
    source_url: str
    score: int
    top_match_reasons: list[str]
    top_gaps: list[str]
    recommended_action: Literal["apply", "maybe", "skip"]


class JobShortlistResponse(BaseModel):
    items: list[JobShortlistItem]


class UserCreate(BaseModel):
    email: str
    password: str
    invite_token: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetRequestResponse(BaseModel):
    ok: bool
    message: str
    reset_url: str | None = None


class PasswordResetConfirm(BaseModel):
    token: str
    password: str


class PasswordResetConfirmResponse(BaseModel):
    ok: bool


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


class ResumeVersionSummary(BaseModel):
    id: str
    name: str
    is_active: bool
    rev: int
    updated_at: datetime


class ResumeDocumentResponse(BaseModel):
    id: str
    kind: str
    name: str
    is_active: bool
    rev: int
    content: ResumeTailorerOutput
    updated_at: datetime


class ResumeContentUpdate(BaseModel):
    base_rev: int
    content: ResumeTailorerOutput


class ResumeVersionCreate(BaseModel):
    name: str = "New version"
    clone_active: bool = True


class ResumeVersionPatch(BaseModel):
    name: str | None = None
    make_active: bool | None = None


class EditRuleCreate(BaseModel):
    mode: Literal["always", "never"]
    text: str
    scope: Literal["resume", "cover_letter", "both"] = "resume"


class EditRuleResponse(BaseModel):
    id: str
    mode: str
    text: str
    scope: str
