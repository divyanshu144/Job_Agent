import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { DiscoveryFeedItem } from "../types";
import { JobCard } from "../components/JobCard";

export function Saved() {
  const [feed, setFeed] = useState<DiscoveryFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSavedJobs()
      .then((res) => { setFeed(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  }, []);

  function handleToggleSave(id: string, saved: boolean) {
    if (!saved) {
      setFeed((prev) => prev.filter((j) => j.id !== id));
      setTotal((prev) => prev - 1);
    }
  }

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Saved</h1>
        <p className="text-sm text-slate-500 mt-1">
          Jobs you've starred from Discover
        </p>
      </div>

      {feed.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">
            <strong className="text-slate-700">{total}</strong> saved job{total !== 1 ? "s" : ""}
          </p>
          <div className="space-y-2">
            {feed.map((job) => (
              <JobCard key={job.id} job={job} onToggleSave={handleToggleSave} />
            ))}
          </div>
        </div>
      )}

      {feed.length === 0 && (
        <div className="text-center py-16 border-2 border-dashed border-slate-200 rounded-xl">
          <p className="text-slate-600 font-medium">No saved jobs yet</p>
          <p className="text-sm text-slate-400 mt-1">
            Star jobs on the Discover page to save them here
          </p>
        </div>
      )}
    </div>
  );
}
