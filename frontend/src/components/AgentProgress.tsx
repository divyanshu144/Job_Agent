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
    row: "border-[rgba(0,0,0,0.04)] bg-white",
    dot: "border-[#d4d4d8] bg-white",
    text: "text-[#9898a8]",
    subtext: "text-[#9898a8]",
  },
  running: {
    label: "Preparing",
    row: "border-[rgba(91,91,214,0.15)] bg-[#fafafe]",
    dot: "border-[rgba(91,91,214,0.2)] bg-[#5b5bd6]",
    text: "text-[#5b5bd6]",
    subtext: "text-[#71717a]",
  },
  done: {
    label: "Complete",
    row: "border-emerald-100 bg-emerald-50",
    dot: "border-emerald-100 bg-emerald-500",
    text: "text-[#0f0f17]",
    subtext: "text-emerald-600",
  },
  error: {
    label: "Failed",
    row: "border-rose-100 bg-rose-50",
    dot: "border-rose-100 bg-rose-500",
    text: "text-rose-700",
    subtext: "text-rose-600",
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
  if (s === "done") return <span className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold text-white ${meta.dot}`}>✓</span>;
  if (s === "error") return <span className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold text-white ${meta.dot}`}>!</span>;
  return <span className={`size-4 shrink-0 rounded-full border ${meta.dot}`} />;
}

export function AgentProgress({ agentStates }: { agentStates: Record<AgentName, AgentStatus> }) {
  return (
    <div className="space-y-2.5">
      {AGENT_ORDER.map((a) => {
        const status = agentStates[a];
        const meta = STATUS_META[status];
        return (
          <div key={a} className={`flex items-center gap-3 rounded-xl border px-3 py-3.5 transition-colors ${meta.row}`}>
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
