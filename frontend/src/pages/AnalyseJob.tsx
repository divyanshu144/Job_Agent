import { useState, useRef, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { streamAnalysis, streamGenerate, api } from "../api/client";
import { AgentProgress } from "../components/AgentProgress";
import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus, PipelineDoneData, AnalysisSummary } from "../types";

const initStates = () =>
  Object.fromEntries(AGENT_ORDER.map((a) => [a, "pending"])) as Record<AgentName, AgentStatus>;

type Phase = "idle" | "evaluating" | "evaluated" | "generating";

export function AnalyseJob() {
  const [jd, setJd] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<AgentName, AgentStatus>>(initStates());
  const [evalResult, setEvalResult] = useState<PipelineDoneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const cancelRef = useRef<(() => void) | null>(null);
  const navigate = useNavigate();

  const running = phase === "evaluating" || phase === "generating";

  const loadHistory = () => {
    api.listHistory().then(setHistory).catch(() => {});
  };
  useEffect(() => { loadHistory(); }, []);

  const submit = () => {
    if (jd.trim().length < 50) { setError("JD must be at least 50 characters."); return; }
    setError(null);
    setPhase("evaluating");
    setStates(initStates());
    setEvalResult(null);
    cancelRef.current = streamAnalysis(jd, {
      onAgentStart: ({ agent }) => setStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: (data) => { setPhase("evaluated"); setEvalResult(data); loadHistory(); },
    });
  };

  const generate = () => {
    if (!evalResult) return;
    setPhase("generating");
    setError(null);
    setStates((p) => ({ ...p, resource_planner: "pending", cover_letter: "pending", resume_tailorer: "pending" }));
    cancelRef.current = streamGenerate(evalResult.analysis_id, {
      onAgentStart: ({ agent }) => setStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: ({ analysis_id }) => navigate(`/results/${analysis_id}`),
    });
  };

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Analyse a Job</h1>
      <textarea
        className="w-full h-48 p-3 rounded-lg border border-slate-300 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="Paste the full job description here…"
        value={jd}
        onChange={(e) => setJd(e.target.value)}
        disabled={running}
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {phase === "idle" && (
        <button
          onClick={submit}
          className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Analyse
        </button>
      )}

      {phase === "evaluating" && (
        <button disabled className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium opacity-50">
          Evaluating…
        </button>
      )}

      {phase === "evaluated" && evalResult && (
        <div className="flex items-center gap-4 flex-wrap">
          <div className="text-2xl font-bold text-slate-900">
            {evalResult.score}
            <span className="text-base font-normal text-slate-500">/100</span>
          </div>
          <button
            onClick={generate}
            className="px-6 py-2 rounded-lg bg-green-600 text-white font-medium hover:bg-green-700"
          >
            Generate Documents
          </button>
          <button
            onClick={() => navigate(`/results/${evalResult.analysis_id}`)}
            className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 text-sm hover:bg-slate-50"
          >
            View Gaps Only
          </button>
        </div>
      )}

      {phase === "generating" && (
        <p className="text-sm text-slate-500">Generating cover letter and resume bullets…</p>
      )}

      {phase !== "idle" && <AgentProgress agentStates={states} />}

      {history.length > 0 && (
        <div className="space-y-2 pt-6 border-t border-slate-200">
          <h2 className="text-sm font-semibold text-slate-700">Your analysed jobs</h2>
          {history.map((item) => (
            <Link
              key={item.id}
              to={`/results/${item.id}`}
              className="block p-3 rounded-lg border hover:bg-slate-50"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">
                    {item.role_type ?? "Analysed job"}
                    {item.company ? <span className="text-slate-500 font-normal"> · {item.company}</span> : null}
                  </p>
                  <p className="text-xs text-slate-400 truncate mt-0.5">{item.jd_text.slice(0, 100)}…</p>
                </div>
                {item.match_score != null && (
                  <span className="shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                    {item.match_score}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString()}</span>
                {item.partial && <span className="text-xs text-amber-600">partial</span>}
                {item.evaluate_only && <span className="text-xs text-slate-400">· evaluation only</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
