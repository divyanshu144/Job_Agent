// Mirrors backend/schemas.py 1:1 — update both files when schemas change
export interface GapItem { skill: string; impact: string; rationale: string; }
export interface ResourceItem { skill: string; courses: string[]; books: string[]; projects: string[]; estimated_hours: number; }
export interface BulletItem { original: string; rewritten: string; rationale: string; }
export interface JobParserOutput { required_skills: string[]; nice_to_have: string[]; years_experience: number | null; role_type: string; seniority: string; company?: string | null; }
export interface MatchScorerOutput { score: number; matched_skills: string[]; missing_skills: string[]; partial_matches: string[]; }
export interface GapAnalystOutput { critical_gaps: GapItem[]; nice_to_have_gaps: GapItem[]; }
export interface ResourcePlannerOutput { gaps: ResourceItem[]; }
export interface CoverLetterOutput { subject: string; body: string; tone_notes: string; }
export interface ResumeTailorerOutput { tailored_bullets: BulletItem[]; }
export interface ProfileResponse { id: string; yaml_data: string; cv_text: string; github_data: string; merged_profile: string; last_refreshed_at: string; github_last_fetched_at: string | null; warnings: string[]; }
export interface ProfileStatusResponse { profile_last_built_at: string; github_last_fetched_at: string | null; github_is_stale: boolean; github_stale_after_days: number; }
export interface GitHubRefreshResponse { repos_updated: number; github_last_fetched_at: string; profile: ProfileResponse; }
export interface AnalysisSummary { id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean; }
export interface AnalysisDetail {
  id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean;
  results: {
    job_parser?: JobParserOutput; match_scorer?: MatchScorerOutput;
    gap_analyst?: GapAnalystOutput; resource_planner?: ResourcePlannerOutput;
    cover_letter?: CoverLetterOutput; resume_tailorer?: ResumeTailorerOutput;
  };
}
export type AgentName = "job_parser"|"match_scorer"|"gap_analyst"|"resource_planner"|"cover_letter"|"resume_tailorer";
export const AGENT_ORDER: AgentName[] = ["job_parser","match_scorer","gap_analyst","resource_planner","cover_letter","resume_tailorer"];
export const PHASE1_AGENTS: AgentName[] = ["job_parser","match_scorer","gap_analyst"];
export const PHASE2_AGENTS: AgentName[] = ["resource_planner","cover_letter","resume_tailorer"];
export type AgentStatus = "pending"|"running"|"done"|"error";
export interface PipelineDoneData { analysis_id: string; score: number; partial: boolean; evaluate_only: boolean; }
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

export interface DiscoveryRun {
  id: string;
  source: string;
  triggered_by: string;
  status: "pending" | "running" | "complete" | "failed";
  started_at: string;
  completed_at: string | null;
  funnel: FunnelMetrics;
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
