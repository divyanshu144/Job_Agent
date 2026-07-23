import type { ProfileResponse, ProfileReviewData, ProfileReviewResponse, AnalysisDetail, AgentName, SSECallbacks, RetryRequest, DiscoveryRun, DiscoveryFeedResponse, DiscoverySources, User, RunCost, CostSummary, Contact, ColdEmailDraft, Feedback, AnalysisSummary, InviteResponse, PasswordResetRequestResponse, CampaignRun, TargetCompany, ResumeDocumentResponse, ResumeVersionSummary, ResumeRevisionSummary, EditRuleResponse, ResumeChatResult, ResumeTailorerOutput } from "../types";

const BASE = "/api";

// Error with the HTTP status attached, so callers can branch on 409/429
// instead of string-matching backend error copy.
export class ApiError extends Error {
  status: number;
  // Parsed `detail` from the error response body, when present. Lets callers branch on
  // structured detail (e.g. a 409's { message, rev, content } or { message, warnings })
  // without re-parsing the response.
  detail?: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// The one way to turn a caught value into display text. Safe for non-Error
// throws (a bare `(err as Error).message` is `undefined` then). Pair with
// `err instanceof ApiError && err.status === ...` when you need to branch.
export function errorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  return fallback;
}

function _detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String(item.msg);
        return null;
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String(detail.message);
  }
  return fallback;
}

async function _errorMessage(r: Response, method: string, path: string): Promise<never> {
  const detail = await r.json().then((j) => j?.detail ?? null).catch(() => null);
  if (r.status === 404 && path === "/profile/review") {
    throw new ApiError(
      "Profile review API is not available on the running backend. Restart the backend so /api/profile/review is registered.",
      r.status,
      detail,
    );
  }
  throw new ApiError(_detailToMessage(detail, `${method} ${path} failed: ${r.status}`), r.status, detail);
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!r.ok) return _errorMessage(r, "GET", path);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!r.ok) return _errorMessage(r, "POST", path);
  return r.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!r.ok) return _errorMessage(r, "PUT", path);
  return r.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!r.ok) return _errorMessage(r, "PATCH", path);
  return r.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE", credentials: "include" });
  if (!r.ok) return _errorMessage(r, "DELETE", path);
}

export const api = {
  getProfile: () => get<ProfileResponse>("/profile"),
  getProfileReview: () => get<ProfileReviewResponse>("/profile/review"),
  saveProfileReview: (reviewData: ProfileReviewData) =>
    put<ProfileReviewResponse>("/profile/review", { review_data: reviewData }),
  saveProfileYaml: (yamlText: string) =>
    put<ProfileResponse>("/profile/yaml", { yaml_text: yamlText }),
  refreshProfile: async (): Promise<ProfileResponse> => {
    const r = await fetch(`${BASE}/profile/refresh`, { method: "POST", credentials: "include" });
    if (!r.ok) return _errorMessage(r, "POST", "/profile/refresh");
    return r.json() as Promise<ProfileResponse>;
  },
  uploadCv: async (file: File): Promise<ProfileResponse> => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${BASE}/profile/cv`, { method: "POST", body: form, credentials: "include" });
    if (!r.ok) return _errorMessage(r, "POST", "/profile/cv");
    return r.json() as Promise<ProfileResponse>;
  },
  getAnalysis: (id: string) => get<AnalysisDetail>(`/analysis/${id}`),
  downloadResumeDocx: async (id: string): Promise<Blob> => {
    const r = await fetch(`${BASE}/analysis/${id}/resume.docx`, { credentials: "include" });
    if (!r.ok) return _errorMessage(r, "GET", `/analysis/${id}/resume.docx`);
    return r.blob();
  },
  downloadResumePdf: async (id: string): Promise<Blob> => {
    const r = await fetch(`${BASE}/analysis/${id}/resume.pdf`, { credentials: "include" });
    if (!r.ok) return _errorMessage(r, "GET", `/analysis/${id}/resume.pdf`);
    return r.blob();
  },
  listHistory: () => get<AnalysisSummary[]>("/history"),
  submitFeedback: (analysisId: string, rating: number, agentName?: string, note?: string) =>
    post<Feedback>("/feedback", { analysis_id: analysisId, rating, agent_name: agentName ?? null, note: note ?? null }),
  triggerDiscovery: async (source: string): Promise<{ run_id: string }> => {
    const r = await fetch(`${BASE}/discovery/run?source=${encodeURIComponent(source)}`, { method: "POST", credentials: "include" });
    if (!r.ok) return _errorMessage(r, "POST", `/discovery/run?source=${source}`);
    return r.json() as Promise<{ run_id: string }>;
  },
  triggerAllDiscovery: async (): Promise<{ run_id: string }> => {
    const r = await fetch(`${BASE}/discovery/run/all`, { method: "POST", credentials: "include" });
    if (!r.ok) return _errorMessage(r, "POST", "/discovery/run/all");
    return r.json() as Promise<{ run_id: string }>;
  },
  triggerBatchDiscovery: async (): Promise<{ run_id: string }> => {
    const r = await fetch(`${BASE}/discovery/run/batch/all`, { method: "POST", credentials: "include" });
    if (!r.ok) return _errorMessage(r, "POST", "/discovery/run/batch/all");
    return r.json() as Promise<{ run_id: string }>;
  },
  getDiscoverySources: () => get<DiscoverySources>("/discovery/sources"),
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
    if (!r.ok) return _errorMessage(r, "PATCH", `/discovery/jobs/${jobId}/save`);
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
      if (r.status === 401) {
        throw new Error(
          "Invalid email or password. If this is your first time here, create an account first.",
        );
      }
      const err = await r.json().catch(() => ({ detail: null }));
      throw new Error(_detailToMessage(err.detail, `Login failed: ${r.status}`));
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
      const err = await r.json().catch(() => ({ detail: null }));
      throw new Error(_detailToMessage(err.detail, `Registration failed: ${r.status}`));
    }
    return r.json() as Promise<User>;
  },
  createInvite: (email?: string) =>
    post<InviteResponse>("/auth/invite", { email: email?.trim() || null }),
  requestPasswordReset: (email: string) =>
    post<PasswordResetRequestResponse>("/auth/password-reset/request", { email }),
  confirmPasswordReset: (token: string, password: string) =>
    post<{ ok: boolean }>("/auth/password-reset/confirm", { token, password }),
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
  runCampaignNow: () => post<{ run_id: string; status: string }>("/campaign/run-now", {}),
  getCampaignRuns: () => get<CampaignRun[]>("/campaign/runs"),
  getTargets: () => get<TargetCompany[]>("/targets"),
  addTarget: (target: { name: string; ats: string; slug: string }) =>
    post<TargetCompany>("/targets", target),
  updateTarget: (targetId: string, active: boolean) =>
    patch<TargetCompany>(`/targets/${targetId}`, { active }),
  deleteTarget: (targetId: string) => del(`/targets/${targetId}`),

  // --- resume editor ---
  getMasterResume: () => get<ResumeDocumentResponse>("/resume"),
  listResumeVersions: () => get<ResumeVersionSummary[]>("/resume/versions"),
  createResumeVersion: (name: string, cloneActive = true) =>
    post<ResumeDocumentResponse>("/resume/versions", { name, clone_active: cloneActive }),
  patchResumeVersion: (id: string, body: { name?: string; make_active?: boolean }) =>
    patch<ResumeDocumentResponse>(`/resume/versions/${id}`, body),
  deleteResumeVersion: (id: string) => del(`/resume/versions/${id}`),
  patchResumeContent: (id: string, baseRev: number, content: ResumeTailorerOutput) =>
    patch<ResumeDocumentResponse>(`/resume/${id}/content`, { base_rev: baseRev, content }),
  // base_rev/target_rev are query params on the backend (not a body) — keep the querystring form.
  undoResume: (id: string, baseRev: number) =>
    post<ResumeDocumentResponse>(`/resume/${id}/undo?base_rev=${baseRev}`, {}),
  restoreResume: (id: string, baseRev: number, targetRev: number) =>
    post<ResumeDocumentResponse>(`/resume/${id}/restore?base_rev=${baseRev}&target_rev=${targetRev}`, {}),
  listResumeRevisions: (id: string) => get<ResumeRevisionSummary[]>(`/resume/${id}/revisions`),
  listEditRules: () => get<EditRuleResponse[]>("/resume/rules"),
  deleteEditRule: (id: string) => del(`/resume/rules/${id}`),
  getAnalysisResume: (analysisId: string) =>
    get<ResumeDocumentResponse>(`/analysis/${analysisId}/resume`),
  saveToMaster: (analysisId: string, name: string | null, confirm: boolean) =>
    post<ResumeDocumentResponse>(`/analysis/${analysisId}/resume/save-to-master`, { name, confirm }),
  retailorAnalysis: (analysisId: string, baseRev: number) =>
    post<ResumeDocumentResponse>(`/analysis/${analysisId}/resume/retailor`, { base_rev: baseRev }),
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

export function retryAnalysis(
  analysisId: string,
  body: RetryRequest,
  callbacks: SSECallbacks,
): () => void {
  return _streamSSE(
    `${BASE}/analysis/${analysisId}/retry`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    callbacks,
  );
}

export interface ResumeChatCallbacks {
  onEditStart?: () => void;
  onEditDone?: (result: ResumeChatResult) => void;
  onEditConflict?: (c: { rev: number; content: ResumeTailorerOutput }) => void;
  onEditError?: (message: string) => void;
  onStreamEnd?: () => void;
}

// Not routed through _streamSSE: that helper's SSECallbacks shape (pipeline_start/
// agent_start/agent_done/pipeline_error/pipeline_done) doesn't fit the chat-edit event
// set, and it has no onStreamEnd hook for cleanup on early/aborted requests. The parse
// loop below mirrors _streamSSE's proven split("\n\n") / split("\n") / startsWith
// framing exactly; only the event switch and callback shape differ.
export function streamResumeChat(
  docId: string,
  baseRev: number,
  instruction: string,
  callbacks: ResumeChatCallbacks,
): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const resp = await fetch(`${BASE}/resume/${docId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_rev: baseRev, instruction }),
        credentials: "include",
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        callbacks.onEditError?.(`Chat request failed (${resp.status})`);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
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
            case "edit_start":
              callbacks.onEditStart?.();
              break;
            case "edit_done":
              callbacks.onEditDone?.(data as ResumeChatResult);
              break;
            case "edit_conflict":
              callbacks.onEditConflict?.(data as { rev: number; content: ResumeTailorerOutput });
              break;
            case "edit_error":
              callbacks.onEditError?.((data as { message?: string }).message ?? "Edit failed");
              break;
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        callbacks.onEditError?.(errorMessage(e));
      }
    } finally {
      callbacks.onStreamEnd?.();
    }
  })();
  return () => controller.abort();
}
