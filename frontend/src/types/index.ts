// Mirrors backend/schemas.py 1:1 — update both files when schemas change
export interface GapItem { skill: string; impact: string; rationale: string; }
export interface ResourceItem { skill: string; courses: string[]; books: string[]; projects: string[]; estimated_hours: number; }
export interface BulletItem { original: string; rewritten: string; rationale: string; }
export interface OmittedItem { field: string; value: string; reason: string; }
export interface ResumeExperienceItem { company?: string | null; role?: string | null; dates?: string | null; bullets: string[]; }
export interface ResumeProjectItem { name: string; description?: string | null; bullets: string[]; }
export interface ResumeEducationItem { institution?: string | null; degree?: string | null; dates?: string | null; }
// validation_warnings is a meta-field (exclude=True in Python) — never present in API responses
export interface ValidationWarning { agent: string; rule: string; detail: string; severity: 'warn' | 'error'; }
export interface JobParserOutput { required_skills: string[]; nice_to_have: string[]; years_experience: number | null; role_type: string; seniority: string; company?: string | null; validation_warnings?: ValidationWarning[]; }
export interface MatchScorerOutput { score: number; matched_skills: string[]; missing_skills: string[]; partial_matches: string[]; validation_warnings?: ValidationWarning[]; }
export interface GapAnalystOutput { critical_gaps: GapItem[]; nice_to_have_gaps: GapItem[]; validation_warnings?: ValidationWarning[]; }
export interface PlannerMeta { total_llm_calls: number; retried_gaps: string[]; low_confidence_gaps: string[]; gap_confidences: Record<string, number>; }
export interface ResourcePlannerOutput { gaps: ResourceItem[]; planner_meta?: PlannerMeta | null; validation_warnings?: ValidationWarning[]; }
export interface CoverLetterOutput { subject: string; body: string; tone_notes: string; validation_warnings?: ValidationWarning[]; }
export interface ResumeTailorerOutput {
  headline: string;
  summary: string;
  skills: string[];
  experience: ResumeExperienceItem[];
  projects: ResumeProjectItem[];
  education: ResumeEducationItem[];
  tailored_bullets: BulletItem[];
  omitted_items: OmittedItem[];
  validation_warnings?: ValidationWarning[];
}
export interface ProfileResponse {
  id: string;
  yaml_data: string;
  cv_text: string;
  merged_profile: string;
  profile_review_data: string;
  review_status: string;
  reviewed_at?: string | null;
  last_refreshed_at: string;
  warnings: string[];
}

export interface ProfileReviewProject {
  name: string;
  description: string;
  highlights: string[];
}

export interface ProfileReviewExperience {
  company: string;
  role: string;
  dates: string;
  highlights: string[];
}

export interface ProfileReviewEducation {
  institution: string;
  degree: string;
  field_of_study: string;
  dates: string;
}

export interface ProfileReviewLink {
  label: string;
  url: string;
}

export interface ProfileWorkPreferences {
  locations: string[];
  remote?: string | null;
  role_types: string[];
  industries: string[];
}

export interface ProfileReviewData {
  target_role: string;
  target_roles: string[];
  key_skills: string[];
  projects: ProfileReviewProject[];
  experience: ProfileReviewExperience[];
  education: ProfileReviewEducation[];
  links: ProfileReviewLink[];
  work_preferences: ProfileWorkPreferences;
}

export interface ProfileReviewResponse {
  profile_id: string;
  review_data: ProfileReviewData;
  review_status: string;
  reviewed_at?: string | null;
  has_cv_text: boolean;
}
export interface AnalysisSummary { id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean; status?: string | null; role_type?: string | null; company?: string | null; match_score?: number | null; profile_stale?: boolean; }
// Per-step status for the retry strip (mirrors backend Step).
export interface Step { name: string; phase: 1 | 2; status: "success" | "error" | "pending"; error_code?: string | null; message?: string | null; }
export interface RetryRequest { agents?: string[]; scope?: "failed" | "all"; }
export interface AnalysisDetail {
  id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean;
  results: {
    job_parser?: JobParserOutput; match_scorer?: MatchScorerOutput;
    gap_analyst?: GapAnalystOutput; resource_planner?: ResourcePlannerOutput;
    cover_letter?: CoverLetterOutput; resume_tailorer?: ResumeTailorerOutput;
  };
  result_errors?: Partial<Record<AgentName, string>>;
  result_contexts?: Partial<Record<AgentName, Record<string, unknown>>>;
  steps?: Step[];
  profile_stale?: boolean;
  current_profile_id?: string | null;
}
export type AgentName = "job_parser"|"match_scorer"|"gap_analyst"|"resource_planner"|"cover_letter"|"resume_tailorer";
export const AGENT_ORDER: AgentName[] = ["job_parser","match_scorer","gap_analyst","resource_planner","cover_letter","resume_tailorer"];
export const PHASE1_AGENTS: AgentName[] = ["job_parser","match_scorer","gap_analyst"];
export const PHASE2_AGENTS: AgentName[] = ["resource_planner","cover_letter","resume_tailorer"];
export type AgentStatus = "pending"|"running"|"done"|"error";
export interface QualitySignals { match_score: number | null; match_score_adjusted: number | null; gaps_critical: number; gaps_nice_to_have: number; resource_confidence_avg: number | null; low_confidence_gaps: string[]; }
export interface PipelineDoneData { analysis_id: string; score: number; partial: boolean; evaluate_only: boolean; quality_signals?: QualitySignals; }
export interface SSECallbacks {
  onPipelineStart?: (data: { total_agents: number }) => void;
  onAgentStart?: (data: { agent: AgentName }) => void;
  onAgentDone?: (data: { agent: AgentName; output: unknown }) => void;
  onPipelineError?: (data: { agent: AgentName; error: string }) => void;
  onPipelineDone?: (data: PipelineDoneData) => void;
}

export interface FunnelMetrics {
  jobs_found: number;
  passed_stage1: number;
  passed_stage2: number;
  scored: number;
}

/** Per-source progress entry inside DiscoveryRun.source_statuses */
export interface SourceStatusItem {
  status: "pending" | "running" | "done" | "failed";
  jobs_found: number;
  jobs_scored: number;
  error: string | null;
}

export interface DiscoveryRun {
  id: string;
  source: string;
  triggered_by: string;
  status: "pending" | "running" | "complete" | "failed";
  started_at: string;
  completed_at: string | null;
  funnel: FunnelMetrics;
  /** Populated for "all" runs; empty object for single-source runs */
  source_statuses: Record<string, SourceStatusItem>;
}

/** Which sources have credentials configured (values are never actual keys) */
export interface DiscoverySources {
  sources: Record<string, boolean>;
}

export interface DiscoveryFeedItem {
  id: string;
  title: string;
  company: string;
  location: string | null;
  source_url: string;
  sources: string[];
  relevance_score: number;
  matched_profiles: string[];
  analysis_id: string | null;
  state: string;
  discovered_at: string;
  saved: boolean;
}

export interface DiscoveryFeedResponse {
  items: DiscoveryFeedItem[];
  total: number;
  has_more: boolean;
}

export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
}

export interface InviteResponse {
  invite_url: string;
  token: string;
  expires_at: string;
}

export interface PasswordResetRequestResponse {
  ok: boolean;
  message: string;
  reset_url?: string | null;
}

export interface AgentCost {
  agent_name: string;
  calls: number;
  cost_usd: number;
  avg_latency_ms: number;
}

export interface RunCost {
  id: string;
  type: "discovery" | "analysis";
  created_at: string;
  total_cost_usd: number;
  total_calls: number;
  cached_calls: number;
  latency_p50_ms: number;
  agents: AgentCost[];
}

export interface CostSummary {
  total_cost_usd: number;
  total_calls: number;
  real_calls: number;
  cached_calls: number;
  cache_hit_rate: number;
  total_input_tokens: number;
  total_output_tokens: number;
  // Model tiering: what Haiku calls would have cost at Sonnet rates
  haiku_cost_usd: number;
  counterfactual_sonnet_cost_usd: number;
  tiering_savings_usd: number;
  tiering_ratio: number;  // counterfactual / actual; 1.0 when no Haiku calls
  // Anthropic prompt caching
  prompt_cache_read_tokens: number;
  prompt_cache_creation_tokens: number;
  prompt_cache_savings_usd: number;
}

export interface Contact {
  id: string;
  analysis_id: string;
  email: string;
  name: string | null;
  title: string | null;
  company: string | null;
  source: string;
  confidence: number;
  status: "discovered" | "drafted" | "sent";
  draft_subject: string | null;
  draft_text: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface ColdEmailDraft {
  subject: string;
  body: string;
}

export interface Feedback {
  id: string;
  analysis_id: string;
  agent_name: string | null;
  rating: number;
  note: string | null;
  trace_id: string | null;
  created_at: string;
}

// Regular-tier campaign — mirrors backend CampaignRunResponse 1:1.
export interface CampaignRun {
  id: string;
  status: string; // running | completed | failed | blocked
  started_at: string;
  finished_at?: string | null;
  jobs_considered: number;
  jobs_drafted: number;
  jobs_failed: number;
  error?: string | null;
}

// Mirrors backend TargetCompanyResponse 1:1.
export interface TargetCompany {
  id: string;
  name: string;
  ats: string; // greenhouse | lever | ashby
  slug: string;
  active: boolean;
  created_at: string;
}

// --- resume editor — mirrors backend/schemas.py 1:1 ---
export interface ResumeVersionSummary {
  id: string;
  name: string;
  is_active: boolean;
  rev: number;
  updated_at: string;
}

export interface ResumeRevisionSummary {
  rev: number;
  source: string;
  summary?: string | null;
  created_at: string;
}

export interface EditRuleResponse {
  id: string;
  mode: string;
  text: string;
  scope: string;
}

export interface ResumeDocumentResponse {
  id: string;
  kind: string;
  name: string;
  is_active: boolean;
  rev: number;
  analysis_id?: string | null;
  created_at: string;
  content: ResumeTailorerOutput;
  updated_at: string;
  warnings: ValidationWarning[];
}

export interface ResumeChatResult {
  rev: number;
  content: ResumeTailorerOutput;
  summary: string;
  warnings: ValidationWarning[];
  new_rule?: EditRuleResponse | null;
  fallback_used: boolean;
}
