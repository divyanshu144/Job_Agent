import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ClipboardList,
  FileText,
  RotateCcw,
  Sparkles,
  Wand2,
} from "lucide-react";
import { api, streamAnalysis, streamGenerate } from "../api/client";
import { AgentProgress } from "../components/AgentProgress";
import { EmptyState, PageShell, Panel, PrimaryButton, SecondaryButton, SectionHeader } from "../components/portal";
import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus, AnalysisSummary, PipelineDoneData } from "../types";

const initStates = () =>
  Object.fromEntries(AGENT_ORDER.map((agent) => [agent, "pending"])) as Record<
    AgentName,
    AgentStatus
  >;

type Phase = "idle" | "evaluating" | "evaluated" | "generating";

const workflowPreview = [
  ["Reviewing role requirements", "Understand responsibilities, skills, and expectations"],
  ["Comparing against your profile", "Assess fit using your saved background"],
  ["Identifying gaps", "Separate important gaps from nice-to-have items"],
  ["Preparing recommendations", "Create practical next steps for this role"],
  ["Drafting documents", "Prepare application materials when requested"],
  ["Finalising package", "Save everything in one application package"],
];

export function AnalyseJob() {
  const [jd, setJd] = useState("");
  const [roleHint, setRoleHint] = useState("");
  const [companyHint, setCompanyHint] = useState("");
  const [tailoringNotes, setTailoringNotes] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<AgentName, AgentStatus>>(initStates());
  const [evalResult, setEvalResult] = useState<PipelineDoneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [technicalError, setTechnicalError] = useState<string | null>(null);
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const cancelRef = useRef<(() => void) | null>(null);
  const navigate = useNavigate();

  const running = phase === "evaluating" || phase === "generating";
  const charCount = jd.trim().length;

  const loadHistory = () => {
    api.listHistory().then((items) => setHistory(items.slice(0, 6))).catch(() => {});
  };

  useEffect(() => {
    loadHistory();
    return () => cancelRef.current?.();
  }, []);

  const submit = () => {
    if (charCount < 50) {
      setError("Paste at least 50 characters from the job description.");
      return;
    }

    const context = [
      roleHint.trim() ? `Role hint: ${roleHint.trim()}` : "",
      companyHint.trim() ? `Company hint: ${companyHint.trim()}` : "",
      tailoringNotes.trim() ? `Tailoring notes: ${tailoringNotes.trim()}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    const payload = context ? `${context}\n\nJob description:\n${jd}` : jd;

    setError(null);
    setTechnicalError(null);
    setPhase("evaluating");
    setStates(initStates());
    setEvalResult(null);
    cancelRef.current = streamAnalysis(payload, {
      onAgentStart: ({ agent }) => setStates((prev) => ({ ...prev, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((prev) => ({ ...prev, [agent]: "done" })),
      onPipelineError: ({ agent, error }) => {
        setStates((prev) => ({ ...prev, [agent]: "error" }));
        setError("The package could not be prepared. Edit the job description and try again.");
        setTechnicalError(error);
      },
      onPipelineDone: (data) => {
        setPhase("evaluated");
        setEvalResult(data);
        loadHistory();
      },
    });
  };

  const generate = () => {
    if (!evalResult) return;
    setPhase("generating");
    setError(null);
    setTechnicalError(null);
    setStates((prev) => ({
      ...prev,
      resource_planner: "pending",
      cover_letter: "pending",
      resume_tailorer: "pending",
    }));
    cancelRef.current = streamGenerate(evalResult.analysis_id, {
      onAgentStart: ({ agent }) => setStates((prev) => ({ ...prev, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((prev) => ({ ...prev, [agent]: "done" })),
      onPipelineError: ({ agent, error }) => {
        setStates((prev) => ({ ...prev, [agent]: "error" }));
        setError("Documents could not be prepared.");
        setTechnicalError(error);
      },
      onPipelineDone: ({ analysis_id }) => navigate(`/results/${analysis_id}`),
    });
  };

  const clear = () => {
    cancelRef.current?.();
    setJd("");
    setRoleHint("");
    setCompanyHint("");
    setTailoringNotes("");
    setPhase("idle");
    setStates(initStates());
    setEvalResult(null);
    setError(null);
    setTechnicalError(null);
  };

  return (
    <PageShell>
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_420px]">
        <Panel>
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div>
              <div className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-500">
                <Sparkles className="size-3.5" />
                Application package request
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-tight text-zinc-950">
                Submit a role for review
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
                Share the role details and any tailoring notes. JobFit will prepare a match
                review and application materials for the opportunity.
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.16em] text-zinc-500">
                Role title
              </span>
              <input
                value={roleHint}
                onChange={(event) => setRoleHint(event.target.value)}
                placeholder="Backend Engineer"
                disabled={running}
                className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-sm text-zinc-950 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600/25"
              />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.16em] text-zinc-500">
                Company
              </span>
              <input
                value={companyHint}
                onChange={(event) => setCompanyHint(event.target.value)}
                placeholder="Acme"
                disabled={running}
                className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-sm text-zinc-950 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600/25"
              />
            </label>
          </div>

          <label className="mt-4 block space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-zinc-500">
              Job description
            </span>
            <textarea
              className="h-72 w-full resize-none rounded-2xl border border-zinc-200 bg-white p-4 text-sm leading-6 text-zinc-950 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600/25"
              placeholder="Paste the full job description here..."
              value={jd}
              onChange={(event) => setJd(event.target.value)}
              disabled={running}
            />
          </label>

          <label className="mt-4 block space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-zinc-500">
              Notes for tailoring
            </span>
            <textarea
              className="h-24 w-full resize-none rounded-xl border border-zinc-200 bg-white p-3 text-sm leading-6 text-zinc-950 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600/25"
              placeholder="Optional: target tone, achievements to emphasize, concerns, or application context."
              value={tailoringNotes}
              onChange={(event) => setTailoringNotes(event.target.value)}
              disabled={running}
            />
          </label>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className={`text-xs ${charCount >= 50 ? "text-zinc-500" : "text-amber-500"}`}>
              {charCount} characters
            </span>
            {error && <span className="text-sm font-medium text-rose-600">{error}</span>}
          </div>

          {technicalError && (
            <details className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm">
              <summary className="cursor-pointer font-medium text-rose-700">Show error details</summary>
              <p className="mt-2 whitespace-pre-wrap text-rose-600">{technicalError}</p>
            </details>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <PrimaryButton
              onClick={submit}
              disabled={running}
            >
              <Wand2 className={`size-4 ${phase === "evaluating" ? "animate-pulse" : ""}`} />
              {phase === "evaluating" ? "Preparing match review..." : "Prepare application package"}
            </PrimaryButton>
            <SecondaryButton
              onClick={clear}
              disabled={running && phase !== "evaluating"}
            >
              <RotateCcw className="size-4" />
              Clear
            </SecondaryButton>

            {phase === "evaluated" && evalResult && (
              <>
                <PrimaryButton
                  onClick={generate}
                  className="bg-emerald-600 hover:bg-emerald-500"
                >
                  <FileText className="size-4" />
                  Prepare documents
                </PrimaryButton>
                <SecondaryButton
                  onClick={() => navigate(`/results/${evalResult.analysis_id}`)}
                >
                  Open package
                  <ArrowRight className="size-4" />
                </SecondaryButton>
              </>
            )}
          </div>
        </Panel>

        <Panel>
          <div className="flex items-center gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl bg-blue-600/15 text-blue-400">
              <ClipboardList className="size-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-zinc-950">Review progress</p>
              <p className="text-xs text-zinc-500">Package preparation steps</p>
            </div>
          </div>

          <div className="mt-5 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
            {phase === "idle" ? (
              <div className="space-y-4">
                {workflowPreview.map(([title, description]) => (
                  <div key={title} className="flex gap-3">
                    <div className="mt-1.5 size-2 rounded-full bg-zinc-700" />
                    <div>
                      <p className="text-sm font-medium text-zinc-800">{title}</p>
                      <p className="text-xs leading-5 text-zinc-500">{description}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <AgentProgress agentStates={states} />
            )}
          </div>

          {phase === "evaluated" && evalResult && (
            <div className="mt-5 rounded-2xl border border-emerald-600/25 bg-emerald-600/10 p-4">
              <p className="text-sm font-semibold text-emerald-700">Match review complete</p>
              <div className="mt-3 flex items-end gap-2">
                <span className="text-4xl font-semibold text-zinc-950">{evalResult.score}</span>
                <span className="pb-1 text-sm text-zinc-500">/100 match score</span>
              </div>
            </div>
          )}

          {phase === "generating" && (
            <div className="mt-5 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm font-medium text-blue-700">
              Preparing cover letter, recommendations, and resume bullets...
            </div>
          )}
        </Panel>
      </section>

      <Panel>
        <SectionHeader
          title="Recent submissions"
          action={
            <Link to="/results" className="text-sm font-medium text-blue-700 hover:text-blue-600">
              View all
            </Link>
          }
        />
        {history.length ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {history.map((item) => (
              <Link
                key={item.id}
                to={`/results/${item.id}`}
                className="group block rounded-2xl border border-zinc-200 bg-zinc-50 p-4 transition-colors hover:border-blue-200"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-zinc-950">
                      {item.role_type ?? "Submitted role"}
                      {item.company ? <span className="font-normal text-zinc-500"> · {item.company}</span> : null}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500">
                      {item.jd_text.slice(0, 140)}...
                    </p>
                  </div>
                  {item.match_score != null && (
                    <span className="shrink-0 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700">
                      {item.match_score}
                    </span>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                  {item.partial && <span className="text-amber-500">partial</span>}
                  {item.evaluate_only && <span>match review</span>}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="No submissions yet" description="Submitted roles will appear here." />
        )}
      </Panel>
    </PageShell>
  );
}
