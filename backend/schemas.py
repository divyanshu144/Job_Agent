from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class AnalysisDetail(BaseModel):
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool
    results: dict[str, dict]  # type: ignore[type-arg]
