import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api/client";
import type { DiscoveryRun, DiscoveryFeedItem, DiscoverySources, FunnelMetrics, SourceStatusItem } from "../types";
import { JobCard } from "../components/JobCard";

const FUNNEL_STEPS: { key: keyof FunnelMetrics; label: string; bar: string }[] = [
  { key: "jobs_found",    label: "Found",    bar: "bg-slate-300"   },
  { key: "passed_stage1", label: "Keyword",  bar: "bg-blue-400"    },
  { key: "passed_stage2", label: "Relevant", bar: "bg-violet-400"  },
  { key: "scored",        label: "Scored",   bar: "bg-emerald-500" },
];

const SOURCE_LABELS: Record<string, string> = { hn: "HN", reed: "Reed", adzuna: "Adzuna" };

const STATUS_BADGE: Record<SourceStatusItem["status"], string> = {
  pending:  "bg-slate-100 text-slate-500",
  running:  "bg-blue-100 text-blue-700",
  done:     "bg-emerald-100 text-emerald-700",
  failed:   "bg-red-100 text-red-700",
};

function SourceBadges({
  sources,
  configured,
  statuses,
}: {
  sources: string[];
  configured: Record<string, boolean>;
  statuses: Record<string, SourceStatusItem>;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {sources.map((src) => {
        const isConfigured = configured[src] ?? false;
        const st = statuses[src];
        const label = SOURCE_LABELS[src] ?? src.toUpperCase();

        if (!isConfigured) {
          return (
            <span
              key={src}
              title="Credentials not configured"
              className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium bg-slate-100 text-slate-400 opacity-50"
            >
              {label}
              <span className="text-slate-300">·</span>
              <span>–</span>
            </span>
          );
        }

        if (!st) {
          return (
            <span
              key={src}
              className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium bg-slate-100 text-slate-500"
            >
              {label}
            </span>
          );
        }

        const badgeClass = STATUS_BADGE[st.status];
        const detail =
          st.status === "failed"
            ? (st.error ?? "failed")
            : st.status === "done"
            ? `${st.jobs_scored} scored`
            : st.status === "running"
            ? `${st.jobs_found} found…`
            : "pending";

        return (
          <span
            key={src}
            title={st.status === "failed" ? (st.error ?? "") : undefined}
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${badgeClass}`}
          >
            {label}
            {st.status === "running" && (
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
              </span>
            )}
            <span className="opacity-70">· {detail}</span>
          </span>
        );
      })}
    </div>
  );
}

function FunnelBar({ run, configured, allSources }: { run: DiscoveryRun; configured: Record<string, boolean>; allSources: string[] }) {
  const f = run.funnel;
  const isRunning = run.status === "running" || run.status === "pending";
  const max = Math.max(f.jobs_found, 1);
  const isMultiSource = run.source === "all";

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
              ? isMultiSource ? "Scanning all sources…" : `Scanning ${(run.source ?? "hn").toUpperCase()} jobs…`
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

      {isMultiSource && (
        <SourceBadges
          sources={allSources}
          configured={configured}
          statuses={run.source_statuses}
        />
      )}

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

const ALL_SOURCES = ["hn", "reed", "adzuna"];

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
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [configuredSources, setConfiguredSources] = useState<Record<string, boolean>>({
    hn: true, reed: false, adzuna: false,
  });
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [timedOutRunId, setTimedOutRunId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const loadFeed = useCallback(async (profile?: string, location?: string) => {
    try {
      const res = await api.getDiscoveryFeed({ profile: profile || undefined, location: location || undefined, offset: 0 });
      setFeed(res.items);
      setTotal(res.total);
      setOffset(res.items.length);
      setHasMore(res.has_more);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Failed to load feed");
    }
  }, []);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const res = await api.getDiscoveryFeed({ profile: profileFilter || undefined, location: locationFilter || undefined, offset });
      setFeed((prev) => [...prev, ...res.items]);
      setOffset((prev) => prev + res.items.length);
      setHasMore(res.has_more);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Failed to load more");
    } finally {
      setLoadingMore(false);
    }
  };

  const refreshRunStatus = async () => {
    if (!timedOutRunId) return;
    try {
      const run = await api.getDiscoveryRun(timedOutRunId);
      setActiveRun(run);
      setLastRun(run);
      if (run.status === "complete") {
        setTimedOut(false);
        setTimedOutRunId(null);
        loadFeed(profileFilter || undefined, locationFilter || undefined);
      }
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Refresh failed");
    }
  };

  useEffect(() => {
    // Load configured sources and prior runs in parallel
    Promise.all([
      api.getDiscoverySources().then((r: DiscoverySources) => setConfiguredSources(r.sources)).catch(() => {}),
      api.getDiscoveryRuns().then((runs) => {
        if (runs.length > 0) {
          setLastRun(runs[0]);
          if (runs[0].status === "complete") loadFeed();
        }
      }),
    ]).finally(() => setLoading(false));
  }, [loadFeed]);

  // Poll until all per-source statuses are terminal (for "all" runs) or overall status is terminal
  const isRunComplete = (run: DiscoveryRun): boolean => {
    if (run.source !== "all") return run.status === "complete" || run.status === "failed";
    const statuses = Object.values(run.source_statuses);
    if (statuses.length === 0) return run.status === "complete" || run.status === "failed";
    return statuses.every((s) => s.status === "done" || s.status === "failed");
  };

  useEffect(() => {
    if (!activeRunId) return;
    attemptsRef.current = 0;
    const MAX_ATTEMPTS = 200; // 200 × 3s = 10 minutes
    pollRef.current = setInterval(async () => {
      attemptsRef.current += 1;
      if (attemptsRef.current > MAX_ATTEMPTS) {
        clearInterval(pollRef.current!);
        setTimedOutRunId(activeRunId);
        setActiveRunId(null);
        setFetching(false);
        setTimedOut(true);
        return;
      }
      try {
        const run = await api.getDiscoveryRun(activeRunId);
        setActiveRun(run);
        if (isRunComplete(run)) {
          clearInterval(pollRef.current!);
          setActiveRunId(null);
          setFetching(false);
          setLastRun(run);
          if (run.status === "complete") loadFeed(profileFilter || undefined, locationFilter || undefined);
        }
      } catch (err) {
        clearInterval(pollRef.current!);
        setActiveRunId(null);
        setFetching(false);
        setFetchError(err instanceof Error ? err.message : "Polling failed");
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId, profileFilter, locationFilter, loadFeed]);

  async function startRun(trigger: () => Promise<{ run_id: string }>) {
    setFetching(true);
    setFetchError(null);
    setActiveRun(null);
    setTimedOut(false);
    setTimedOutRunId(null);
    try {
      const { run_id } = await trigger();
      setActiveRunId(run_id);
    } catch (err) {
      setFetching(false);
      setFetchError(err instanceof Error ? err.message : "Failed to start discovery");
    }
  }
  const triggerFetch = () => startRun(api.triggerAllDiscovery);
  const triggerBatch = () => startRun(api.triggerBatchDiscovery);

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
    <div className="mx-auto max-w-3xl space-y-6 p-0 sm:p-6">
      <div className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Discover</h1>
          <p className="text-sm text-slate-500 mt-1">
            Job boards · scored for your profiles
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center">
          <button
            onClick={triggerFetch}
            disabled={fetching}
            className="rounded-lg bg-indigo-950 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-900 disabled:opacity-50"
          >
            {fetching ? "Fetching…" : "Fetch All Jobs"}
          </button>
          <button
            onClick={triggerBatch}
            disabled={fetching}
            title="Uses Anthropic Batch API — results arrive asynchronously, funnel will update as batches complete"
            className="rounded-lg border border-indigo-300 px-4 py-2 text-sm font-semibold text-indigo-800 transition-colors hover:bg-indigo-50 disabled:opacity-50"
          >
            Batch mode (50% cheaper)
          </button>
        </div>
      </div>

      {fetchError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {fetchError}
        </div>
      )}

      {timedOut && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex items-center justify-between gap-3">
          <span>Discovery is taking longer than expected. Refresh to check status.</span>
          <button
            onClick={refreshRunStatus}
            className="shrink-0 px-3 py-1 border border-amber-300 rounded-md text-amber-800 hover:bg-amber-100 font-medium"
          >
            Refresh
          </button>
        </div>
      )}

      {displayRun && (
        <FunnelBar
          run={displayRun}
          configured={configuredSources}
          allSources={ALL_SOURCES}
        />
      )}

      {feed.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-500">
              <strong className="text-slate-700">{total}</strong> matched job{total !== 1 ? "s" : ""}
            </p>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <input
                type="text"
                value={locationFilter}
                onChange={(e) => handleLocationFilter(e.target.value)}
                placeholder="Filter by location…"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 sm:w-44"
              />
              {allProfiles.length > 1 && (
                <select
                  value={profileFilter}
                  onChange={(e) => handleProfileFilter(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-200"
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
          {hasMore && (
            <div className="text-center pt-2">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="px-4 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
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
            Fetch jobs from all configured sources
          </p>
        </div>
      )}
    </div>
  );
}
