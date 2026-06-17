import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus } from "../types";

const LABELS: Record<AgentName, string> = {
  job_parser: "Reviewing role requirements",
  match_scorer: "Comparing against your profile",
  gap_analyst: "Identifying gaps",
  resource_planner: "Preparing recommendations",
  cover_letter: "Drafting documents",
  resume_tailorer: "Finalising package",
};

const STATUS_META: Record<AgentStatus, { label: string; row: string; dot: string; text: string; subtext: string }> = {
  pending: {
    label: "Waiting",
    row: "border-zinc-200 bg-white",
    dot: "border-zinc-300 bg-zinc-200",
    text: "text-zinc-700",
    subtext: "text-zinc-500",
  },
  running: {
    label: "Running",
    row: "border-blue-500/35 bg-blue-600/15",
    dot: "border-blue-200 bg-blue-500",
    text: "text-blue-900",
    subtext: "text-blue-700",
  },
  done: {
    label: "Done",
    row: "border-emerald-600/35 bg-emerald-600/15",
    dot: "border-emerald-200 bg-emerald-500",
    text: "text-emerald-900",
    subtext: "text-emerald-700",
  },
  error: {
    label: "Failed",
    row: "border-rose-300/40 bg-rose-400/15",
    dot: "border-rose-100 bg-rose-300",
    text: "text-rose-900",
    subtext: "text-rose-700",
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
  if (s === "done") return <span className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold text-zinc-950 ${meta.dot}`}>✓</span>;
  if (s === "error") return <span className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold text-zinc-950 ${meta.dot}`}>!</span>;
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
