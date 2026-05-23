import type { ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse, AnalysisSummary, AnalysisDetail, AgentName, SSECallbacks } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  getProfile: () => get<ProfileResponse>("/profile"),
  refreshProfile: async (): Promise<ProfileResponse> => {
    const r = await fetch(`${BASE}/profile/refresh`, { method: "POST" });
    if (!r.ok) throw new Error(`Refresh failed: ${r.status}`);
    return r.json() as Promise<ProfileResponse>;
  },
  uploadCv: async (file: File): Promise<ProfileResponse> => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${BASE}/profile/cv`, { method: "POST", body: form });
    if (!r.ok) throw new Error(`CV upload failed: ${r.status}`);
    return r.json() as Promise<ProfileResponse>;
  },
  getProfileStatus: () => get<ProfileStatusResponse>("/profile/status"),
  refreshGithub: async (): Promise<GitHubRefreshResponse> => {
    const r = await fetch(`${BASE}/profile/refresh/github`, { method: "POST" });
    if (!r.ok) throw new Error(`GitHub refresh failed: ${r.status}`);
    return r.json() as Promise<GitHubRefreshResponse>;
  },
  listHistory: (limit = 20, offset = 0) => get<AnalysisSummary[]>(`/history?limit=${limit}&offset=${offset}`),
  getAnalysis: (id: string) => get<AnalysisDetail>(`/analysis/${id}`),
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
