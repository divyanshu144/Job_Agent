import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api/client";
import type { DiscoveryRun, DiscoveryFeedItem, FunnelMetrics } from "../types";
import { JobCard } from "../components/JobCard";

const FUNNEL_STEPS: { key: keyof FunnelMetrics; label: string; bar: string }[] = [
  { key: "jobs_found",    label: "Found",    bar: "bg-slate-300"   },
  { key: "passed_stage1", label: "Keyword",  bar: "bg-blue-400"    },
  { key: "passed_stage2", label: "Relevant", bar: "bg-violet-400"  },
  { key: "scored",        label: "Scored",   bar: "bg-emerald-500" },
];

function FunnelBar({ run }: { run: DiscoveryRun }) {
  const f = run.funnel;
  const isRunning = run.status === "running" || run.status === "pending";
  const max = Math.max(f.jobs_found, 1);

  return (
    <div className="rounded-xl border bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
          )}
          <span className="text-sm font-semibold text-slate-700">
            {isRunning
              ? "Scanning HN jobs…"
              : run.status === "complete"
              ? `Done · ${new Date(run.completed_at!).toLocaleDateString("en-US", { month: "short", day: "numeric" })} at ${new Date(run.completed_at!).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`
              : run.status === "failed"
              ? "Fetch failed — check server logs"
              : "Starting…"}
          </span>
        </div>
        <span className="text-xs text-slate-400">
          <strong className="text-slate-700 font-semibold">{f.scored}</strong> scored this run
        </span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {FUNNEL_STEPS.map((step) => {
          const value = f[step.key];
          const pct = Math.round((value / max) * 100);
          return (
            <div key={step.key} className="space-y-1.5">
              <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${step.bar}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-base font-bold text-slate-800">{value}</span>
              <span className="text-xs text-slate-400 block">{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Discover() {
  const [lastRun, setLastRun] = useState<DiscoveryRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<DiscoveryRun | null>(null);
  const [feed, setFeed] = useState<DiscoveryFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [profileFilter, setProfileFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFeed = useCallback(async (profile?: string, location?: string) => {
    const res = await api.getDiscoveryFeed({ profile: profile || undefined, location: location || undefined });
    setFeed(res.items);
    setTotal(res.total);
  }, []);

  useEffect(() => {
    api.getDiscoveryRuns()
      .then((runs) => {
        if (runs.length > 0) {
          setLastRun(runs[0]);
          if (runs[0].status === "complete") loadFeed();
        }
      })
      .finally(() => setLoading(false));
  }, [loadFeed]);

  useEffect(() => {
    if (!activeRunId) return;
    pollRef.current = setInterval(async () => {
      const run = await api.getDiscoveryRun(activeRunId);
      setActiveRun(run);
      if (run.status === "complete" || run.status === "failed") {
        clearInterval(pollRef.current!);
        setActiveRunId(null);
        setFetching(false);
        setLastRun(run);
        if (run.status === "complete") loadFeed(profileFilter || undefined, locationFilter || undefined);
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeRunId, profileFilter, locationFilter, loadFeed]);

  async function triggerFetch() {
    setFetching(true);
    setActiveRun(null);
    const { run_id } = await api.triggerDiscovery("hn");
    setActiveRunId(run_id);
  }

  function handleProfileFilter(value: string) {
    setProfileFilter(value);
    loadFeed(value || undefined, locationFilter || undefined);
  }

  function handleLocationFilter(value: string) {
    setLocationFilter(value);
    loadFeed(profileFilter || undefined, value || undefined);
  }

  function handleToggleSave(id: string, saved: boolean) {
    setFeed((prev) => prev.map((j) => (j.id === id ? { ...j, saved } : j)));
  }

  const displayRun = activeRun || lastRun;
  const allProfiles = Array.from(new Set(feed.flatMap((j) => j.matched_profiles)));

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Discover</h1>
          <p className="text-sm text-slate-500 mt-1">
            HN "Who is Hiring?" · scored for your profiles
          </p>
        </div>
        <button
          onClick={triggerFetch}
          disabled={fetching}
          className="shrink-0 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {fetching ? "Fetching…" : "Fetch HN Jobs"}
        </button>
      </div>

      {displayRun && <FunnelBar run={displayRun} />}

      {feed.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">
              <strong className="text-slate-700">{total}</strong> matched job{total !== 1 ? "s" : ""}
            </p>
            <div className="flex gap-2 items-center">
              <input
                type="text"
                value={locationFilter}
                onChange={(e) => handleLocationFilter(e.target.value)}
                placeholder="Filter by location…"
                className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 w-44"
              />
              {allProfiles.length > 1 && (
                <select
                  value={profileFilter}
                  onChange={(e) => handleProfileFilter(e.target.value)}
                  className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
                >
                  <option value="">All profiles</option>
                  {allProfiles.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
          <div className="space-y-2">
            {feed.map((job) => (
              <JobCard key={job.id} job={job} onToggleSave={handleToggleSave} />
            ))}
          </div>
        </div>
      )}

      {feed.length === 0 && lastRun?.status === "complete" && (
        <div className="text-center py-16 border-2 border-dashed border-slate-200 rounded-xl">
          <p className="text-slate-500">No matched jobs found.</p>
          <p className="text-xs text-slate-400 mt-1">
            Adjust <code className="bg-slate-100 px-1 py-0.5 rounded">search_profiles</code> in{" "}
            <code className="bg-slate-100 px-1 py-0.5 rounded">data/candidate_profile.yaml</code>
          </p>
        </div>
      )}

      {!displayRun && (
        <div className="text-center py-16 border-2 border-dashed border-slate-200 rounded-xl">
          <p className="text-slate-600 font-medium">No runs yet</p>
          <p className="text-sm text-slate-400 mt-1">
            Fetch jobs from the latest HN "Who is Hiring?" thread
          </p>
        </div>
      )}
    </div>
  );
}
