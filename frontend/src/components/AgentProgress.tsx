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

function Icon({ s }: { s: AgentStatus }) {
  if (s === "pending") return <span className="w-4 h-4 rounded-full bg-slate-200 inline-block" />;
  if (s === "running") return <span className="w-4 h-4 rounded-full bg-blue-400 animate-pulse inline-block" />;
  if (s === "done") return <span className="text-green-500">✓</span>;
  return <span className="text-red-500">✗</span>;
}

export function AgentProgress({ agentStates }: { agentStates: Record<AgentName, AgentStatus> }) {
  return (
    <div className="space-y-2">
      {AGENT_ORDER.map((a) => (
        <div key={a} className="flex items-center gap-3 p-2 rounded-md bg-slate-50">
          <Icon s={agentStates[a]} />
          <span className="text-sm font-medium text-slate-700">{LABELS[a]}</span>
        </div>
      ))}
    </div>
  );
}
