import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { CampaignRun, TargetCompany, AnalysisSummary } from "../types";

const STATUS_BADGE: Record<string, string> = {
  running: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  blocked: "bg-amber-100 text-amber-800",
};

const ATS_OPTIONS = ["greenhouse", "lever", "ashby"];

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;
}

function RunRow({ run }: { run: CampaignRun }) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3 flex items-center gap-3 text-sm">
      <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium shrink-0 ${STATUS_BADGE[run.status] ?? "bg-slate-100 text-slate-500"}`}>
        {run.status === "running" && (
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
          </span>
        )}
        {run.status}
      </span>
      <span className="text-slate-600">{fmt(run.started_at)}</span>
      <span className="text-slate-400">→ {fmt(run.finished_at)}</span>
      <span className="ml-auto text-xs text-slate-500 shrink-0">
        <strong className="text-slate-700">{run.jobs_considered}</strong> considered ·{" "}
        <strong className="text-emerald-700">{run.jobs_drafted}</strong> drafted ·{" "}
        <strong className={run.jobs_failed > 0 ? "text-red-700" : "text-slate-700"}>{run.jobs_failed}</strong> failed
      </span>
      {run.error && <span className="text-xs text-red-700 shrink-0" title={run.error}>· {run.error}</span>}
    </div>
  );
}

export function Campaign() {
  const [runs, setRuns] = useState<CampaignRun[]>([]);
  const [targets, setTargets] = useState<TargetCompany[]>([]);
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [name, setName] = useState("");
  const [ats, setAts] = useState(ATS_OPTIONS[0]);
  const [slug, setSlug] = useState("");
  const [targetError, setTargetError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const loadAll = useCallback(async () => {
    const [runsRes, targetsRes, historyRes] = await Promise.allSettled([
      api.getCampaignRuns(),
      api.getTargets(),
      api.listHistory(),
    ]);
    if (runsRes.status === "fulfilled") {
      setRuns(runsRes.value);
      const active = runsRes.value.find((r) => r.status === "running");
      if (active) setActiveRunId(active.id); // resume polling after reload
    }
    if (targetsRes.status === "fulfilled") setTargets(targetsRes.value);
    if (historyRes.status === "fulfilled") setHistory(historyRes.value.slice(0, 10));
    const failed = [runsRes, targetsRes, historyRes].find((r) => r.status === "rejected");
    if (failed && failed.status === "rejected") {
      setError(failed.reason instanceof Error ? failed.reason.message : "Failed to load campaign data");
    }
  }, []);

  useEffect(() => {
    loadAll().finally(() => setLoading(false));
  }, [loadAll]);

  // Poll runs while one is active; stop on terminal state or timeout.
  useEffect(() => {
    if (!activeRunId) return;
    attemptsRef.current = 0;
    const MAX_ATTEMPTS = 200; // 200 × 3s = 10 minutes
    pollRef.current = setInterval(async () => {
      attemptsRef.current += 1;
      if (attemptsRef.current > MAX_ATTEMPTS) {
        clearInterval(pollRef.current!);
        setActiveRunId(null);
        setTimedOut(true);
        return;
      }
      try {
        const latest = await api.getCampaignRuns();
        setRuns(latest);
        const run = latest.find((r) => r.id === activeRunId);
        if (run && run.status !== "running") {
          clearInterval(pollRef.current!);
          setActiveRunId(null);
          if (run.status === "blocked") {
            setNotice(run.error ?? "Run blocked by your usage caps.");
          }
          loadAll();
        }
      } catch (err) {
        // 429 (own rate limit, e.g. several tabs polling) is transient — skip
        // this tick and keep polling instead of abandoning the run.
        if (err instanceof ApiError && err.status === 429) return;
        clearInterval(pollRef.current!);
        setActiveRunId(null);
        setError(err instanceof Error ? err.message : "Polling failed");
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId]);

  async function handleRunNow() {
    setStarting(true);
    setError(null);
    setNotice(null);
    setTimedOut(false);
    try {
      const { run_id } = await api.runCampaignNow();
      setActiveRunId(run_id);
      const latest = await api.getCampaignRuns().catch(() => null);
      if (latest) setRuns(latest);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to start run";
      // 409 is expected when a run is in flight — informational, not an error.
      if (err instanceof ApiError && err.status === 409) {
        setNotice(msg);
        loadAll();
      } else {
        setError(msg);
      }
    } finally {
      setStarting(false);
    }
  }

  async function handleAddTarget(e: React.FormEvent) {
    e.preventDefault();
    setTargetError(null);
    try {
      const created = await api.addTarget({ name: name.trim(), ats, slug: slug.trim() });
      setTargets((prev) => [...prev, created]);
      setName("");
      setSlug("");
    } catch (err) {
      setTargetError(err instanceof Error ? err.message : "Failed to add target");
    }
  }

  async function handleToggleTarget(t: TargetCompany) {
    try {
      const updated = await api.updateTarget(t.id, !t.active);
      setTargets((prev) => prev.map((x) => (x.id === t.id ? updated : x)));
    } catch (err) {
      setTargetError(err instanceof Error ? err.message : "Failed to update target");
    }
  }

  async function handleDeleteTarget(id: string) {
    try {
      await api.deleteTarget(id);
      setTargets((prev) => prev.filter((x) => x.id !== id));
    } catch (err) {
      setTargetError(err instanceof Error ? err.message : "Failed to delete target");
    }
  }

  const running = activeRunId !== null;
  const activeTargets = targets.filter((t) => t.active).length;

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Campaign</h1>
          <p className="text-sm text-slate-500 mt-1">
            Scans your target companies and prepares application materials overnight, or on demand
          </p>
        </div>
        <button
          onClick={handleRunNow}
          disabled={starting || running}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors shrink-0"
        >
          {running ? "Running…" : starting ? "Starting…" : "Run now"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {notice && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {notice}
        </div>
      )}

      {timedOut && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex items-center justify-between gap-3">
          <span>The run is taking longer than expected. Refresh to check status.</span>
          <button
            onClick={() => { setTimedOut(false); loadAll(); }}
            className="shrink-0 px-3 py-1 border border-amber-300 rounded-md text-amber-800 hover:bg-amber-100 font-medium"
          >
            Refresh
          </button>
        </div>
      )}

      <div className="rounded-xl border bg-white p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">Target companies</h2>
          <span className="text-xs text-slate-400">
            <strong className="text-slate-700 font-semibold">{activeTargets}</strong> active
          </span>
        </div>

        {targetError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {targetError}
          </div>
        )}

        {targets.length === 0 ? (
          <p className="text-sm text-slate-400">
            No targets yet — add a company below. Nightly runs only happen when you have at least one active target.
          </p>
        ) : (
          <div className="space-y-2">
            {targets.map((t) => (
              <div key={t.id} className="flex items-center gap-3 text-sm border border-slate-200 rounded-lg px-3 py-2">
                <span className={`font-medium ${t.active ? "text-slate-800" : "text-slate-400"}`}>{t.name}</span>
                <span className="text-xs text-slate-400">{t.ats} · {t.slug}</span>
                <div className="ml-auto flex items-center gap-2">
                  <button
                    onClick={() => handleToggleTarget(t)}
                    className={`text-xs px-2 py-1 rounded-md border transition-colors ${t.active ? "border-emerald-200 text-emerald-700 hover:bg-emerald-50" : "border-slate-200 text-slate-500 hover:bg-slate-50"}`}
                  >
                    {t.active ? "Active" : "Paused"}
                  </button>
                  <button
                    onClick={() => handleDeleteTarget(t.id)}
                    className="text-xs px-2 py-1 rounded-md border border-slate-200 text-slate-500 hover:text-red-700 hover:border-red-200 transition-colors"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={handleAddTarget} className="flex flex-wrap gap-2 items-center pt-1">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Company name"
            required
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 w-44"
          />
          <select
            value={ats}
            onChange={(e) => setAts(e.target.value)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
          >
            {ATS_OPTIONS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="ATS slug (e.g. stripe)"
            required
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 w-44"
          />
          <button
            type="submit"
            className="px-4 py-2 border border-blue-600 text-blue-700 text-sm font-semibold rounded-lg hover:bg-blue-50 transition-colors"
          >
            Add target
          </button>
        </form>
      </div>

      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Run history</h2>
        {runs.length === 0 ? (
          <div className="text-center py-10 border-2 border-dashed border-slate-200 rounded-xl">
            <p className="text-slate-600 font-medium">No runs yet</p>
            <p className="text-sm text-slate-400 mt-1">Add targets, then hit Run now — or wait for the nightly run</p>
          </div>
        ) : (
          <div className="space-y-2">
            {runs.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </div>
        )}
      </div>

      {history.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Recent materials</h2>
          <div className="space-y-2">
            {history.map((h) => (
              <Link
                key={h.id}
                to={`/results/${h.id}`}
                className="flex items-center gap-3 text-sm border border-slate-200 rounded-lg px-4 py-3 bg-white hover:bg-slate-50 transition-colors"
              >
                <span className="font-medium text-slate-800">
                  {h.company ?? h.role_type ?? h.jd_text.slice(0, 60)}
                </span>
                {h.match_score != null && (
                  <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100">
                    score {h.match_score}
                  </span>
                )}
                <span className="ml-auto text-xs text-slate-400">{fmt(h.created_at)}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
