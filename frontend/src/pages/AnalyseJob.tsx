import { useState, useRef, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight, BriefcaseBusiness, ClipboardList, FileText, Sparkles, Wand2 } from "lucide-react";
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
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
        <div className="grid gap-0 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6 p-6 md:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
                  <Sparkles className="size-3.5" />
                  Two-phase AI pipeline
                </div>
                <h1 className="text-2xl font-bold text-slate-950 md:text-3xl">Analyse a job</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  Paste a role description, evaluate your fit, then generate tailored application
                  materials from the same persisted analysis.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="font-semibold text-slate-900">Parse</p>
                  <p className="text-slate-500">JD</p>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2">
                  <p className="font-semibold text-amber-900">Score</p>
                  <p className="text-amber-700">Fit</p>
                </div>
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2">
                  <p className="font-semibold text-emerald-900">Create</p>
                  <p className="text-emerald-700">Docs</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
              <textarea
                className="h-72 w-full resize-none rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800 shadow-sm shadow-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-300"
                placeholder="Paste the full job description here..."
                value={jd}
                onChange={(e) => setJd(e.target.value)}
                disabled={running}
              />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1">
                <span className="text-xs text-slate-500">{jd.trim().length} characters</span>
                {error && <span className="text-sm font-medium text-red-600">{error}</span>}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {phase === "idle" && (
                <button
                  onClick={submit}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-950 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-900"
                >
                  <Wand2 className="size-4" />
                  Analyse fit
                </button>
              )}

              {phase === "evaluating" && (
                <button disabled className="inline-flex items-center gap-2 rounded-lg bg-indigo-950 px-5 py-2.5 text-sm font-semibold text-white opacity-60">
                  <Wand2 className="size-4 animate-pulse" />
                  Evaluating...
                </button>
              )}

              {phase === "evaluated" && evalResult && (
                <>
                  <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 shadow-sm">
                    <span className="text-xs font-medium text-slate-500">Fit score</span>
                    <span className="text-2xl font-bold text-slate-950">
                      {evalResult.score}
                      <span className="text-sm font-normal text-slate-500">/100</span>
                    </span>
                  </div>
                  <button
                    onClick={generate}
                    className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700"
                  >
                    <FileText className="size-4" />
                    Generate documents
                  </button>
                  <button
                    onClick={() => navigate(`/results/${evalResult.analysis_id}`)}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    View gaps
                    <ArrowRight className="size-4" />
                  </button>
                </>
              )}

              {phase === "generating" && (
                <p className="inline-flex items-center gap-2 text-sm font-medium text-slate-600">
                  <FileText className="size-4 animate-pulse" />
                  Generating cover letter and resume bullets...
                </p>
              )}
            </div>
          </div>

          <aside className="border-t border-indigo-100 bg-indigo-950 p-6 text-white lg:border-l lg:border-t-0 md:p-8">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-lg bg-white text-slate-950">
                <ClipboardList className="size-5" />
              </div>
              <div>
                <p className="text-sm font-semibold">Pipeline status</p>
                <p className="text-xs text-slate-400">Live SSE agent progress</p>
              </div>
            </div>
            <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
              {phase === "idle" ? (
                <div className="space-y-4">
                  {[
                    ["Job parser", "Extracts role, seniority, skills"],
                    ["Match scorer", "Scores fit against your profile"],
                    ["Gap analyst", "Identifies missing skills"],
                    ["Document agents", "Generate materials after approval"],
                  ].map(([title, desc]) => (
                    <div key={title} className="flex gap-3">
                      <div className="mt-1 size-2 rounded-full bg-slate-500" />
                      <div>
                        <p className="text-sm font-medium text-white">{title}</p>
                        <p className="text-xs text-slate-400">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <AgentProgress agentStates={states} />
              )}
            </div>
          </aside>
        </div>
      </section>

      {history.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <BriefcaseBusiness className="size-4 text-slate-500" />
              <h2 className="text-sm font-semibold text-slate-800">Recent analyses</h2>
            </div>
            <span className="text-xs text-slate-400">{history.length} saved</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {history.map((item) => (
              <Link
                key={item.id}
                to={`/results/${item.id}`}
                className="group block rounded-xl border border-slate-200 bg-slate-50 p-4 transition-colors hover:border-slate-300 hover:bg-white"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-950">
                      {item.role_type ?? "Analysed job"}
                      {item.company ? <span className="font-normal text-slate-500"> · {item.company}</span> : null}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{item.jd_text.slice(0, 140)}...</p>
                  </div>
                  {item.match_score != null && (
                    <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800">
                      {item.match_score}
                    </span>
                  )}
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString()}</span>
                  {item.partial && <span className="text-xs font-medium text-amber-600">partial</span>}
                  {item.evaluate_only && <span className="text-xs text-slate-400">evaluation only</span>}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
