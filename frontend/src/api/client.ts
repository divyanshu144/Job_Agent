import type { ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse, AnalysisDetail, AgentName, SSECallbacks, DiscoveryRun, DiscoveryFeedResponse, User, RunCost, CostSummary, Contact, ColdEmailDraft } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!r.ok) throw new Error(`POST ${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  getProfile: () => get<ProfileResponse>("/profile"),
  refreshProfile: async (): Promise<ProfileResponse> => {
    const r = await fetch(`${BASE}/profile/refresh`, { method: "POST", credentials: "include" });
    if (!r.ok) throw new Error(`Refresh failed: ${r.status}`);
    return r.json() as Promise<ProfileResponse>;
  },
  uploadCv: async (file: File): Promise<ProfileResponse> => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${BASE}/profile/cv`, { method: "POST", body: form, credentials: "include" });
    if (!r.ok) throw new Error(`CV upload failed: ${r.status}`);
    return r.json() as Promise<ProfileResponse>;
  },
  getProfileStatus: () => get<ProfileStatusResponse>("/profile/status"),
  refreshGithub: async (): Promise<GitHubRefreshResponse> => {
    const r = await fetch(`${BASE}/profile/refresh/github`, { method: "POST", credentials: "include" });
    if (!r.ok) throw new Error(`GitHub refresh failed: ${r.status}`);
    return r.json() as Promise<GitHubRefreshResponse>;
  },
  getAnalysis: (id: string) => get<AnalysisDetail>(`/analysis/${id}`),
  triggerDiscovery: async (source: string): Promise<{ run_id: string }> => {
    const r = await fetch(`${BASE}/discovery/run?source=${source}`, { method: "POST", credentials: "include" });
    if (!r.ok) throw new Error(`Trigger discovery failed: ${r.status}`);
    return r.json() as Promise<{ run_id: string }>;
  },
  getDiscoveryRun: (runId: string) => get<DiscoveryRun>(`/discovery/runs/${runId}`),
  getDiscoveryRuns: () => get<DiscoveryRun[]>("/discovery/runs"),
  getDiscoveryFeed: (params: { profile?: string; location?: string; minScore?: number; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.profile) q.set("profile", params.profile);
    if (params.location) q.set("location", params.location);
    if (params.minScore !== undefined) q.set("min_score", String(params.minScore));
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return get<DiscoveryFeedResponse>(`/discovery/feed${qs ? "?" + qs : ""}`);
  },
  getSavedJobs: () => get<DiscoveryFeedResponse>("/discovery/saved"),
  saveJob: async (jobId: string): Promise<{ id: string; saved: boolean }> => {
    const r = await fetch(`${BASE}/discovery/jobs/${jobId}/save`, { method: "PATCH", credentials: "include" });
    if (!r.ok) throw new Error(`Save job failed: ${r.status}`);
    return r.json() as Promise<{ id: string; saved: boolean }>;
  },
  getMe: async (): Promise<User | null> => {
    try {
      return await get<User>("/auth/me");
    } catch {
      return null;
    }
  },
  login: async (email: string, password: string): Promise<User> => {
    const r = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      credentials: "include",
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(err.detail || "Login failed");
    }
    return r.json() as Promise<User>;
  },
  register: async (email: string, password: string, inviteToken?: string): Promise<User> => {
    const r = await fetch(`${BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, invite_token: inviteToken }),
      credentials: "include",
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Registration failed" }));
      throw new Error(err.detail || "Registration failed");
    }
    return r.json() as Promise<User>;
  },
  logout: async (): Promise<void> => {
    await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
  },
  getCostSummary: () => get<CostSummary>("/metrics/costs/summary"),
  getCostRuns: () => get<RunCost[]>("/metrics/costs/runs"),
  getContacts: (analysisId: string) =>
    get<Contact[]>(`/contacts?analysis_id=${analysisId}`),
  discoverContacts: (analysisId: string, domain?: string) =>
    post<Contact[]>("/contacts/discover", { analysis_id: analysisId, domain: domain ?? null }),
  draftEmail: (contactId: string) =>
    post<ColdEmailDraft>(`/contacts/${contactId}/draft`, {}),
  sendEmail: (contactId: string) =>
    post<{ sent: boolean }>(`/contacts/${contactId}/send`, {}),
};

function _streamSSE(url: string, init: RequestInit, callbacks: SSECallbacks): () => void {
  const controller = new AbortController();
  (async () => {
    const resp = await fetch(url, { ...init, signal: controller.signal });
    if (!resp.body) return;
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          if (!chunk.trim()) continue;
          const lines = chunk.split("\n");
          const eventLine = lines.find((l) => l.startsWith("event:"));
          const dataLine = lines.find((l) => l.startsWith("data:"));
          if (!eventLine || !dataLine) continue;
          const eventName = eventLine.replace("event:", "").trim();
          const data = JSON.parse(dataLine.replace("data:", "").trim());
          switch (eventName) {
            case "pipeline_start": callbacks.onPipelineStart?.(data); break;
            case "agent_start": callbacks.onAgentStart?.(data as { agent: AgentName }); break;
            case "agent_done": callbacks.onAgentDone?.(data); break;
            case "pipeline_error": callbacks.onPipelineError?.(data); break;
            case "pipeline_done":
              callbacks.onPipelineDone?.(data);
              controller.abort();
              return;
          }
        }
      }
    } catch (e) { if ((e as Error).name !== "AbortError") throw e; }
  })();
  return () => controller.abort();
}

export function streamAnalysis(jd: string, callbacks: SSECallbacks): () => void {
  return _streamSSE(
    `${BASE}/analyse`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jd }) },
    callbacks,
  );
}

export function streamGenerate(analysisId: string, callbacks: SSECallbacks): () => void {
  return _streamSSE(`${BASE}/analyse/generate/${analysisId}`, { method: "POST" }, callbacks);
}
