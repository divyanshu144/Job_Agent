import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from "react";
import { api, errorMessage, ApiError } from "../api/client";
import type { DiscoveryRun, DiscoveryFeedItem, DiscoverySources, FunnelMetrics, SourceStatusItem, ProfileReviewResponse } from "../types";
import { JobCard } from "../components/JobCard";
import { X } from "lucide-react";

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

// Reusable chip-input, matches the skills chip pattern from ProfileSetup
function ChipInput({
  chips,
  draft,
  placeholder,
  onDraftChange,
  onAdd,
  onRemove,
  chipColor = "indigo",
}: {
  chips: string[];
  draft: string;
  placeholder: string;
  onDraftChange: (v: string) => void;
  onAdd: (v: string) => void;
  onRemove: (i: number) => void;
  chipColor?: "indigo" | "violet";
}) {
  const colorMap = {
    indigo: {
      chip: "border-indigo-200 bg-indigo-50 text-indigo-700",
      btn: "text-indigo-500 hover:bg-indigo-100 hover:text-indigo-700",
    },
    violet: {
      chip: "border-violet-200 bg-violet-50 text-violet-700",
      btn: "text-violet-500 hover:bg-violet-100 hover:text-violet-700",
    },
  };
  const c = colorMap[chipColor];

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      onAdd(draft);
    } else if (e.key === "Backspace" && !draft && chips.length > 0) {
      onRemove(chips.length - 1);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 min-h-[2rem]">
        {chips.map((chip, i) => (
          <span
            key={`${chip}-${i}`}
            className={`inline-flex items-center gap-1.5 rounded-full border py-1 pl-3 pr-1.5 text-sm font-medium ${c.chip}`}
          >
            {chip}
            <button
              type="button"
              onClick={() => onRemove(i)}
              aria-label={`Remove ${chip}`}
              className={`grid size-5 place-items-center rounded-full transition-colors ${c.btn}`}
            >
              <X className="size-3.5" />
            </button>
          </span>
        ))}
        {chips.length === 0 && (
          <span className="text-sm text-slate-400 self-center">None yet</span>
        )}
      </div>
      <input
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => onAdd(draft)}
        className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300/50"
        placeholder={placeholder}
      />
    </div>
  );
}

// Panel shown when search criteria (target_roles + locations) are not yet configured
function SearchSetupPanel({
  review,
  onSaved,
}: {
  review: ProfileReviewResponse;
  onSaved: () => void;
}) {
  const rd = review.review_data;
  const [roles, setRoles] = useState<string[]>(rd.target_roles ?? []);
  const [locations, setLocations] = useState<string[]>(rd.work_preferences?.locations ?? []);
  const [roleDraft, setRoleDraft] = useState("");
  const [locationDraft, setLocationDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const addRole = (v: string) => {
    const val = v.trim();
    if (!val) return;
    const already = roles.some((r) => r.toLowerCase() === val.toLowerCase());
    if (!already) setRoles((prev) => [...prev, val]);
    setRoleDraft("");
  };

  const addLocation = (v: string) => {
    const val = v.trim();
    if (!val) return;
    const already = locations.some((l) => l.toLowerCase() === val.toLowerCase());
    if (!already) setLocations((prev) => [...prev, val]);
    setLocationDraft("");
  };

  const addRemote = () => addLocation("Remote");

  const handleSave = async () => {
    if (roles.length === 0 || locations.length === 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.saveProfileReview({
        ...rd,
        target_roles: roles,
        work_preferences: {
          ...(rd.work_preferences ?? { remote: "", role_types: [], industries: [] }),
          locations,
        },
      });
      onSaved();
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const canSave = roles.length > 0 && locations.length > 0;

  return (
    <div className="rounded-xl border border-indigo-100 bg-white shadow-sm overflow-hidden">
      <div className="border-b border-slate-100 bg-gradient-to-r from-indigo-50 to-violet-50 px-6 py-5">
        <h2 className="text-base font-semibold text-slate-900">Set up your search</h2>
        <p className="mt-0.5 text-sm text-slate-500">
          Tell us what roles and locations to scan so the discovery pipeline knows what to surface for you.
        </p>
      </div>

      <div className="space-y-6 px-6 py-5">
        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-700">
            Target roles
            <span className="ml-1 text-xs font-normal text-slate-400">(at least one required)</span>
          </label>
          <ChipInput
            chips={roles}
            draft={roleDraft}
            placeholder="e.g. Software Engineer, Product Manager — press Enter to add"
            onDraftChange={setRoleDraft}
            onAdd={addRole}
            onRemove={(i) => setRoles((prev) => prev.filter((_, idx) => idx !== i))}
            chipColor="indigo"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <label className="block text-sm font-medium text-slate-700">
              Preferred locations
              <span className="ml-1 text-xs font-normal text-slate-400">(at least one required)</span>
            </label>
            {!locations.some((l) => l.toLowerCase() === "remote") && (
              <button
                type="button"
                onClick={addRemote}
                className="text-xs font-medium text-indigo-600 hover:text-indigo-500 underline underline-offset-2"
              >
                + Add Remote
              </button>
            )}
          </div>
          <ChipInput
            chips={locations}
            draft={locationDraft}
            placeholder="e.g. London, New York — press Enter to add"
            onDraftChange={setLocationDraft}
            onAdd={addLocation}
            onRemove={(i) => setLocations((prev) => prev.filter((_, idx) => idx !== i))}
            chipColor="violet"
          />
        </div>

        {saveError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {saveError}
          </p>
        )}

        <button
          type="button"
          onClick={handleSave}
          disabled={!canSave || saving}
          className="rounded-lg bg-indigo-950 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-900 disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save search criteria"}
        </button>
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
  // Search criteria state
  const [reviewData, setReviewData] = useState<ProfileReviewResponse | null>(null);
  const [hasCriteria, setHasCriteria] = useState(true); // optimistic until loaded
  const [showSetup, setShowSetup] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const deriveCriteria = (r: ProfileReviewResponse) => {
    const rd = r.review_data;
    return (
      Array.isArray(rd.target_roles) && rd.target_roles.length > 0 &&
      Array.isArray(rd.work_preferences?.locations) && rd.work_preferences.locations.length > 0
    );
  };

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

  // Load profile review + discovery runs in parallel on mount
  useEffect(() => {
    Promise.all([
      api.getProfileReview().then((r) => {
        setReviewData(r);
        const ok = deriveCriteria(r);
        setHasCriteria(ok);
        if (!ok) setShowSetup(true);
      }).catch(() => {
        // If the review endpoint is unavailable, don't block discovery
        setHasCriteria(true);
      }),
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
      // If backend says criteria are missing (422), show the setup panel
      if (err instanceof ApiError && err.status === 422) {
        setShowSetup(true);
        setFetchError(err.message);
      } else {
        setFetchError(err instanceof Error ? err.message : "Failed to start discovery");
      }
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

  // Called after the setup panel saves successfully — re-derive criteria
  const handleCriteriaSaved = async () => {
    try {
      const r = await api.getProfileReview();
      setReviewData(r);
      const ok = deriveCriteria(r);
      setHasCriteria(ok);
      if (ok) {
        setShowSetup(false);
        setFetchError(null);
      }
    } catch {
      // best-effort: just hide the panel and let the user try
      setHasCriteria(true);
      setShowSetup(false);
      setFetchError(null);
    }
  };

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
            disabled={fetching || !hasCriteria}
            title={!hasCriteria ? "Set up your search criteria first" : undefined}
            className="rounded-lg bg-indigo-950 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-900 disabled:opacity-50"
          >
            {fetching ? "Fetching…" : "Fetch All Jobs"}
          </button>
          <button
            onClick={triggerBatch}
            disabled={fetching || !hasCriteria}
            title={!hasCriteria ? "Set up your search criteria first" : "Uses Anthropic Batch API — results arrive asynchronously, funnel will update as batches complete"}
            className="rounded-lg border border-indigo-300 px-4 py-2 text-sm font-semibold text-indigo-800 transition-colors hover:bg-indigo-50 disabled:opacity-50"
          >
            Batch mode (50% cheaper)
          </button>
        </div>
      </div>

      {/* Setup panel — shown when criteria are missing or after a 422 */}
      {showSetup && reviewData && (
        <SearchSetupPanel review={reviewData} onSaved={handleCriteriaSaved} />
      )}

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

      {feed.length === 0 && lastRun?.status === "complete" && !showSetup && (
        <div className="text-center py-16 border-2 border-dashed border-slate-200 rounded-xl">
          <p className="text-slate-500">No matched jobs found.</p>
          <p className="text-xs text-slate-400 mt-1">
            Try adjusting your target roles or locations in the search setup above.
          </p>
        </div>
      )}

      {!displayRun && !showSetup && (
        <div className="text-center py-16 border-2 border-dashed border-slate-200 rounded-xl">
          <p className="text-slate-600 font-medium">No runs yet</p>
          <p className="text-sm text-slate-400 mt-1">
            Fetch jobs from all configured sources
          </p>
        </div>
      )}

      {!displayRun && showSetup && (
        <div className="text-center py-8 border-2 border-dashed border-slate-200 rounded-xl">
          <p className="text-slate-500 text-sm">Set up your search to start discovering jobs</p>
        </div>
      )}
    </div>
  );
}
