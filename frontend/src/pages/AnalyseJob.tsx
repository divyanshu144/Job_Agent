import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { streamAnalysis, streamGenerate } from "../api/client";
import { AgentProgress } from "../components/AgentProgress";
import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus, PipelineDoneData } from "../types";

const initStates = () =>
  Object.fromEntries(AGENT_ORDER.map((a) => [a, "pending"])) as Record<AgentName, AgentStatus>;

type Phase = "idle" | "evaluating" | "evaluated" | "generating";

export function AnalyseJob() {
  const [jd, setJd] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<AgentName, AgentStatus>>(initStates());
  const [evalResult, setEvalResult] = useState<PipelineDoneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const navigate = useNavigate();

  const running = phase === "evaluating" || phase === "generating";

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
      onPipelineDone: (data) => { setPhase("evaluated"); setEvalResult(data); },
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
    </div>
  );
}
