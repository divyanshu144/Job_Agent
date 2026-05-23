import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { api, streamGenerate } from "../api/client";
import type { AnalysisDetail, AgentName, AgentStatus } from "../types";
import { PHASE2_AGENTS } from "../types";
import { ScoreCard } from "../components/ScoreCard";
import { GapList } from "../components/GapList";
import { ResourcePanel } from "../components/ResourcePanel";
import { DocViewer } from "../components/DocViewer";

type Tab = "score" | "gaps" | "resources" | "letter" | "resume";
const TABS: { id: Tab; label: string }[] = [
  { id: "score", label: "Score" },
  { id: "gaps", label: "Gaps" },
  { id: "resources", label: "Resources" },
  { id: "letter", label: "Cover Letter" },
  { id: "resume", label: "Resume" },
];

export function Results() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [tab, setTab] = useState<Tab>("score");
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genStates, setGenStates] = useState<Partial<Record<AgentName, AgentStatus>>>({});
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (id) api.getAnalysis(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

  const generate = () => {
    if (!data) return;
    setGenerating(true);
    setGenStates(Object.fromEntries(PHASE2_AGENTS.map((a) => [a, "pending"])));
    cancelRef.current = streamGenerate(data.id, {
      onAgentStart: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: () => {
        api.getAnalysis(data.id).then(setData).finally(() => setGenerating(false));
      },
    });
  };

  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!data) return <p className="p-6 text-slate-500">Loading…</p>;
  const r = data.results;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Results</h1>
      {data.partial && (
        <p className="text-amber-600 text-sm">⚠ Partial results — some agents failed.</p>
      )}

      {data.evaluate_only && !generating && (
        <div className="flex items-center gap-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-800 flex-1">
            Evaluation complete. Generate your cover letter, resource plan, and resume bullets.
          </p>
          <button
            onClick={generate}
            className="shrink-0 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
          >
            Generate Documents
          </button>
        </div>
      )}

      {generating && (
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <p className="text-sm text-slate-600 mb-2">Generating documents…</p>
          <div className="flex gap-3 text-xs text-slate-500">
            {PHASE2_AGENTS.map((a) => (
              <span
                key={a}
                className={
                  genStates[a] === "done"
                    ? "text-green-600"
                    : genStates[a] === "running"
                    ? "text-blue-600"
                    : ""
                }
              >
                {a.replace("_", " ")} {genStates[a] === "done" ? "✓" : genStates[a] === "running" ? "…" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === t.id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="pt-2">
        {tab === "score" && r.match_scorer && (
          <ScoreCard
            score={r.match_scorer.score}
            matched={r.match_scorer.matched_skills}
            missing={r.match_scorer.missing_skills}
            partial={r.match_scorer.partial_matches}
          />
        )}
        {tab === "gaps" && r.gap_analyst && (
          <GapList
            critical={r.gap_analyst.critical_gaps}
            niceToHave={r.gap_analyst.nice_to_have_gaps}
          />
        )}
        {tab === "resources" && (
          r.resource_planner
            ? <ResourcePanel gaps={r.resource_planner.gaps} />
            : <p className="text-sm text-slate-400 italic">Generate documents to see resource plan.</p>
        )}
        {tab === "letter" && (
          r.cover_letter
            ? <DocViewer title="Cover Letter" content={r.cover_letter.body} filename="cover_letter.txt" />
            : <p className="text-sm text-slate-400 italic">Generate documents to see cover letter.</p>
        )}
        {tab === "resume" && (
          r.resume_tailorer
            ? (
              <div className="space-y-4">
                {r.resume_tailorer.tailored_bullets.map((b, i) => (
                  <div key={i} className="border rounded-lg p-4 space-y-2 text-sm">
                    <p className="text-slate-400 line-through">{b.original}</p>
                    <p className="text-slate-900 font-medium">{b.rewritten}</p>
                    <p className="text-xs text-slate-400 italic">{b.rationale}</p>
                  </div>
                ))}
              </div>
            )
            : <p className="text-sm text-slate-400 italic">Generate documents to see resume bullets.</p>
        )}
      </div>
    </div>
  );
}
