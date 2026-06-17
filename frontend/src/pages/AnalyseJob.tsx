import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, CheckCircle2, ChevronDown, ChevronUp, Circle, Sparkles } from "lucide-react";
import { api, streamAnalysis, streamGenerate } from "../api/client";
import { AgentProgress } from "../components/AgentProgress";
import { EmptyState, PageShell } from "../components/portal";
import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus, AnalysisSummary, PipelineDoneData } from "../types";

const initStates = () =>
  Object.fromEntries(AGENT_ORDER.map((agent) => [agent, "pending"])) as Record<AgentName, AgentStatus>;

type Phase = "idle" | "evaluating" | "evaluated" | "generating";

const previewSteps = [
  ["Reviewing role requirements", "Extracting requirements and seniority signals"],
  ["Comparing against your profile", "Matching the role to your saved background"],
  ["Identifying gaps", "Finding skills to develop or address"],
  ["Preparing recommendations", "Creating practical next steps"],
  ["Drafting documents", "Preparing cover letter and resume materials"],
  ["Finalising package", "Saving your application package"],
];

export function AnalyseJob() {
  const [jd, setJd] = useState("");
  const [roleHint, setRoleHint] = useState("");
  const [companyHint, setCompanyHint] = useState("");
  const [tailoringNotes, setTailoringNotes] = useState("");
  const [showOptional, setShowOptional] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<AgentName, AgentStatus>>(initStates());
  const [evalResult, setEvalResult] = useState<PipelineDoneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [technicalError, setTechnicalError] = useState<string | null>(null);
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const cancelRef = useRef<(() => void) | null>(null);
  const navigate = useNavigate();

  const wordCount = jd.trim() ? jd.trim().split(/\s+/).filter(Boolean).length : 0;
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
    ].filter(Boolean).join("\n");
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
    setShowOptional(false);
    setPhase("idle");
    setStates(initStates());
    setEvalResult(null);
    setError(null);
    setTechnicalError(null);
  };

  if (phase === "evaluating" || phase === "evaluated" || phase === "generating") {
    return (
      <PageShell width="medium">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">Submit Role</p>
          <h1 className="text-2xl font-medium tracking-[-0.03em] text-[#0f0f17]">
            {phase === "evaluating" ? "Preparing your package..." : phase === "generating" ? "Preparing documents..." : "Package ready"}
          </h1>
          <p className="mt-1 text-sm text-[#71717a]">
            {roleHint || "Submitted role"} {companyHint ? `· ${companyHint}` : ""}
          </p>
        </div>

        <div className="overflow-hidden rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white">
          <AgentProgress agentStates={states} />
        </div>

        {phase === "evaluated" && evalResult && (
          <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-6">
            <div className="flex items-center gap-6">
              <div className="relative flex size-24 shrink-0 items-center justify-center">
                <svg className="-rotate-90" width={96} height={96}>
                  <circle cx={48} cy={48} r={40} fill="none" stroke="rgba(91,91,214,0.12)" strokeWidth={7} />
                  <circle
                    cx={48}
                    cy={48}
                    r={40}
                    fill="none"
                    stroke={evalResult.score >= 80 ? "#16a34a" : "#5b5bd6"}
                    strokeWidth={7}
                    strokeDasharray={2 * Math.PI * 40}
                    strokeDashoffset={2 * Math.PI * 40 * (1 - evalResult.score / 100)}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="font-mono text-2xl leading-none text-[#5b5bd6]">{evalResult.score}</span>
                  <span className="mt-0.5 font-mono text-[10px] text-[#71717a]">MATCH</span>
                </div>
              </div>
              <div className="flex-1">
                <h3 className="mb-1 text-base font-medium text-[#0f0f17]">Match review complete</h3>
                <p className="text-sm leading-relaxed text-[#71717a]">
                  Your match review is ready. Prepare the application documents or open the package.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full border border-[rgba(91,91,214,0.15)] bg-[#ededf8] px-2 py-0.5 text-[11px] text-[#5b5bd6]">
                    Match score ready
                  </span>
                  <span className="rounded-full border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">
                    Saved package
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {error && <div className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div>}
        {technicalError && (
          <details className="rounded-xl border border-rose-100 bg-rose-50 p-3 text-sm">
            <summary className="cursor-pointer text-rose-700">Show error details</summary>
            <p className="mt-2 whitespace-pre-wrap text-rose-600">{technicalError}</p>
          </details>
        )}

        <div className="flex gap-3">
          {phase === "evaluated" && (
            <button onClick={generate} className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28]">
              Prepare documents
              <ArrowRight className="size-3.5" />
            </button>
          )}
          {phase === "evaluated" && evalResult && (
            <button onClick={() => navigate(`/results/${evalResult.analysis_id}`)} className="rounded-xl border border-[rgba(0,0,0,0.08)] px-4 py-2.5 text-sm text-[#71717a] transition-colors hover:border-[rgba(0,0,0,0.15)]">
              Open package
            </button>
          )}
          <button onClick={clear} className="rounded-xl border border-[rgba(0,0,0,0.08)] px-4 py-2.5 text-sm text-[#71717a] transition-colors hover:border-[rgba(0,0,0,0.15)]">
            {phase === "evaluated" ? "New Role" : "Cancel"}
          </button>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell width="medium">
      <div>
        <p className="mb-1 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">Submit Role</p>
        <h1 className="text-2xl font-medium tracking-[-0.03em] text-[#0f0f17]">Submit a role for review</h1>
        <p className="mt-1 text-sm text-[#71717a]">
          Paste a job description and JobFit will prepare your application package.
        </p>
      </div>

      <div className="space-y-4">
        <div className="overflow-hidden rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white transition-all focus-within:border-[#5b5bd6] focus-within:ring-4 focus-within:ring-[rgba(91,91,214,0.08)]">
          <div className="flex items-center justify-between border-b border-[rgba(0,0,0,0.04)] px-4 pb-2 pt-4">
            <label className="font-mono text-xs uppercase tracking-wide text-[#71717a]">Job Description</label>
          </div>
          <textarea
            value={jd}
            onChange={(event) => setJd(event.target.value)}
            placeholder="Paste the full job description here..."
            rows={12}
            className="w-full resize-none bg-transparent px-4 py-3 text-sm leading-relaxed text-[#0f0f17] outline-none placeholder:text-[#9898a8]"
          />
          <div className="flex items-center justify-between border-t border-[rgba(0,0,0,0.04)] px-4 py-2">
            <span className={`font-mono text-xs ${charCount >= 50 ? "text-[#9898a8]" : "text-amber-600"}`}>
              {wordCount > 0 ? `${wordCount} words` : "Minimum 50 characters required"}
            </span>
            {jd && (
              <button onClick={() => setJd("")} className="text-xs text-[#9898a8] transition-colors hover:text-[#71717a]">
                Clear
              </button>
            )}
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white">
          <button
            onClick={() => setShowOptional(!showOptional)}
            className="flex w-full items-center justify-between px-4 py-3.5 text-left transition-colors hover:bg-[#fafafa]"
          >
            <span className="text-sm text-[#0f0f17]">Optional details</span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#9898a8]">Role, company, notes</span>
              {showOptional ? <ChevronUp className="size-3.5 text-[#71717a]" /> : <ChevronDown className="size-3.5 text-[#71717a]" />}
            </div>
          </button>
          {showOptional && (
            <div className="grid gap-3 border-t border-[rgba(0,0,0,0.04)] px-4 pb-4 sm:grid-cols-2">
              <InputBlock label="Role Title" value={roleHint} onChange={setRoleHint} placeholder="e.g. Backend Engineer" />
              <InputBlock label="Company" value={companyHint} onChange={setCompanyHint} placeholder="e.g. Stripe" />
              <label className="space-y-1.5 sm:col-span-2">
                <span className="font-mono text-xs uppercase tracking-wide text-[#71717a]">Notes</span>
                <textarea
                  value={tailoringNotes}
                  onChange={(event) => setTailoringNotes(event.target.value)}
                  placeholder="Optional: context, achievements to emphasize, or application notes."
                  rows={3}
                  className="w-full resize-none rounded-lg border border-[rgba(0,0,0,0.06)] bg-[#f7f7f5] px-3 py-2 text-sm text-[#0f0f17] outline-none transition-all placeholder:text-[#9898a8] focus:border-[#5b5bd6] focus:ring-2 focus:ring-[rgba(91,91,214,0.08)]"
                />
              </label>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-[rgba(91,91,214,0.1)] bg-[rgba(91,91,214,0.04)] p-4">
          <p className="mb-2 font-mono text-xs uppercase tracking-wide text-[#5b5bd6]">What happens next</p>
          <div className="grid gap-2 sm:grid-cols-3">
            {previewSteps.map(([title], index) => (
              <div key={title} className="flex items-center gap-2">
                {index < 3 ? <CheckCircle2 className="size-4 text-[#5b5bd6]" /> : <Circle className="size-4 text-[#d4d4d8]" />}
                <span className="text-xs leading-tight text-[#71717a]">{title}</span>
              </div>
            ))}
          </div>
        </div>

        {error && <div className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div>}

        <button
          onClick={submit}
          disabled={!jd.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-3 text-sm font-medium text-white transition-all hover:bg-[#1a1a28] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Sparkles className="size-4" />
          Prepare application package
          <ArrowRight className="size-3.5" />
        </button>
      </div>

      {history.length ? (
        <div className="grid gap-3 md:grid-cols-2">
          {history.slice(0, 4).map((item) => (
            <Link key={item.id} to={`/results/${item.id}`} className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-4 transition-all hover:shadow-sm">
              <p className="truncate text-sm text-[#0f0f17]">{item.role_type ?? "Submitted role"}</p>
              <p className="mt-1 truncate text-xs text-[#71717a]">{item.company ?? new Date(item.created_at).toLocaleString()}</p>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState title="No submissions yet" description="Submitted roles will appear here." />
      )}
    </PageShell>
  );
}

function InputBlock({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="space-y-1.5 pt-3">
      <span className="font-mono text-xs uppercase tracking-wide text-[#71717a]">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-[rgba(0,0,0,0.06)] bg-[#f7f7f5] px-3 py-2 text-sm text-[#0f0f17] outline-none transition-all placeholder:text-[#9898a8] focus:border-[#5b5bd6] focus:ring-2 focus:ring-[rgba(91,91,214,0.08)]"
      />
    </label>
  );
}
