import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, streamGenerate } from "../api/client";
import type { DiscoveryFeedItem } from "../types";

export function ScoreBadge({ score }: { score: number }) {
  const cls =
    score >= 70 ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
    score >= 50 ? "bg-amber-50 text-amber-700 border-amber-200" :
                  "bg-slate-50 text-slate-600 border-slate-200";
  return (
    <div className={`w-11 h-11 shrink-0 rounded-full border-2 flex items-center justify-center font-bold text-sm ${cls}`}>
      {score}
    </div>
  );
}

export function JobCard({
  job,
  onToggleSave,
}: {
  job: DiscoveryFeedItem;
  onToggleSave?: (id: string, saved: boolean) => void;
}) {
  const navigate = useNavigate();
  const [generating, setGenerating] = useState(false);
  const [saved, setSaved] = useState(job.saved);

  function handleSave(e: React.MouseEvent) {
    e.stopPropagation();
    const next = !saved;
    setSaved(next);
    api.saveJob(job.id)
      .then(() => onToggleSave?.(job.id, next))
      .catch(() => setSaved(!next)); // revert on error
  }

  function handleCardClick() {
    if (job.analysis_id) navigate(`/results/${job.analysis_id}`);
  }

  function handleGenerate(e: React.MouseEvent) {
    e.stopPropagation();
    if (!job.analysis_id) return;
    setGenerating(true);
    streamGenerate(job.analysis_id, {
      onPipelineDone: (data) => {
        setGenerating(false);
        navigate(`/results/${data.analysis_id}`);
      },
      onPipelineError: () => setGenerating(false),
    });
  }

  return (
    <div
      onClick={handleCardClick}
      className={`flex gap-3 p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm transition-all ${job.analysis_id ? "cursor-pointer" : ""}`}
    >
      <ScoreBadge score={job.relevance_score} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-900 leading-snug">
              {job.title || "Unknown role"}
            </h3>
            <p className="text-sm text-slate-500 mt-0.5">
              <span className="font-medium text-slate-600">{job.company || "Unknown"}</span>
              {job.location && <> · {job.location}</>}
            </p>
          </div>
          <div className="flex gap-1.5 shrink-0 mt-0.5">
            <button
              onClick={handleSave}
              title={saved ? "Unsave" : "Save"}
              className={`text-base px-2 py-0.5 rounded-md border transition-colors ${
                saved
                  ? "text-amber-500 border-amber-200 bg-amber-50 hover:bg-amber-100"
                  : "text-slate-300 border-slate-200 hover:text-amber-400 hover:border-amber-200"
              }`}
            >
              {saved ? "★" : "☆"}
            </button>
            <a
              href={job.source_url || "#"}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-xs text-slate-500 hover:text-slate-800 px-2.5 py-1 border border-slate-200 rounded-md hover:border-slate-300 transition-colors"
            >
              View ↗
            </a>
            {job.analysis_id && (
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="text-xs bg-blue-600 text-white px-3 py-1 rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium"
              >
                {generating ? "Generating…" : "Generate docs"}
              </button>
            )}
          </div>
        </div>
        {job.matched_profiles.length > 0 && (
          <div className="flex gap-1 mt-2.5 flex-wrap">
            {job.matched_profiles.map((p) => (
              <span
                key={p}
                className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100 font-medium"
              >
                {p}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
