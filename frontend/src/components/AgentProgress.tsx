import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus } from "../types";

const LABELS: Record<AgentName, string> = {
  job_parser: "Parse Job",
  match_scorer: "Score Match",
  gap_analyst: "Analyse Gaps",
  resource_planner: "Plan Resources",
  cover_letter: "Write Cover Letter",
  resume_tailorer: "Tailor Resume",
};

const STATUS_META: Record<AgentStatus, { label: string; row: string; dot: string; text: string; subtext: string }> = {
  pending: {
    label: "Waiting",
    row: "border-white/10 bg-white/6",
    dot: "border-white/15 bg-white/20",
    text: "text-indigo-100",
    subtext: "text-indigo-200/70",
  },
  running: {
    label: "Running",
    row: "border-sky-300/40 bg-sky-400/15 shadow-sm shadow-sky-950/20",
    dot: "border-sky-200 bg-sky-300",
    text: "text-white",
    subtext: "text-sky-100",
  },
  done: {
    label: "Done",
    row: "border-emerald-300/35 bg-emerald-400/15",
    dot: "border-emerald-100 bg-emerald-300",
    text: "text-white",
    subtext: "text-emerald-100",
  },
  error: {
    label: "Failed",
    row: "border-red-300/40 bg-red-400/15",
    dot: "border-red-100 bg-red-300",
    text: "text-white",
    subtext: "text-red-100",
  },
};

function Icon({ s }: { s: AgentStatus }) {
  const meta = STATUS_META[s];
  if (s === "running") {
    return (
      <span className="relative flex size-4 shrink-0">
        <span className={`absolute inline-flex size-full animate-ping rounded-full opacity-60 ${meta.dot}`} />
        <span className={`relative inline-flex size-4 rounded-full border ${meta.dot}`} />
      </span>
    );
  }
  if (s === "done") return <span className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold text-indigo-950 ${meta.dot}`}>✓</span>;
  if (s === "error") return <span className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold text-indigo-950 ${meta.dot}`}>!</span>;
  return <span className={`size-4 shrink-0 rounded-full border ${meta.dot}`} />;
}

export function AgentProgress({ agentStates }: { agentStates: Record<AgentName, AgentStatus> }) {
  return (
    <div className="space-y-2.5">
      {AGENT_ORDER.map((a) => {
        const status = agentStates[a];
        const meta = STATUS_META[status];
        return (
          <div key={a} className={`flex items-center gap-3 rounded-xl border px-3 py-3 transition-colors ${meta.row}`}>
            <Icon s={status} />
            <div className="min-w-0 flex-1">
              <p className={`truncate text-sm font-semibold ${meta.text}`}>{LABELS[a]}</p>
              <p className={`text-xs ${meta.subtext}`}>{meta.label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
