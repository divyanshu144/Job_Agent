import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Clock, FileSearch, Search, SlidersHorizontal } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, PageShell, StatusPill } from "../components/portal";
import { ScoreRing } from "../components/ScoreRing";
import type { StatusTone } from "../components/portal";
import type { AnalysisSummary } from "../types";

type Filter = "all" | "documents" | "partial";

const filters: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "documents", label: "Complete" },
  { id: "partial", label: "Partial" },
];

export function MyResults() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    api
      .listHistory()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      const haystack = `${item.role_type ?? ""} ${item.company ?? ""} ${item.jd_text}`.toLowerCase();
      const matchesQuery = !q || haystack.includes(q);
      const matchesFilter =
        filter === "all" ||
        (filter === "documents" && !item.evaluate_only && !item.partial) ||
        (filter === "partial" && item.partial);
      return matchesQuery && matchesFilter;
    });
  }, [filter, items, query]);

  const completeCount = items.filter((item) => !item.evaluate_only && !item.partial).length;
  const scores = items.map((item) => item.match_score).filter((score): score is number => typeof score === "number");
  const average = scores.length ? Math.round(scores.reduce((total, score) => total + score, 0) / scores.length) : null;

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">
            My Packages
          </p>
          <h1 className="text-2xl font-medium tracking-[-0.03em] text-[#0f0f17]">Application Packages</h1>
          <p className="mt-1 text-sm text-[#71717a]">
            {items.length} packages · {completeCount} complete
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-[#ededf8] px-2.5 py-1 font-mono text-xs text-[#5b5bd6]">
            Avg {average == null ? "--" : `${average}%`}
          </span>
          <Link
            to="/analyse"
            className="hidden items-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28] sm:flex"
          >
            <FileSearch className="size-3.5" />
            New Package
          </Link>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-[#9898a8]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by role or company..."
            className="w-full rounded-xl border border-[rgba(0,0,0,0.06)] bg-white py-2.5 pl-9 pr-4 text-sm text-[#0f0f17] outline-none transition-all placeholder:text-[#9898a8] focus:border-[#5b5bd6] focus:ring-4 focus:ring-[rgba(91,91,214,0.06)]"
          />
        </label>
        <div className="flex gap-1 rounded-xl border border-[rgba(0,0,0,0.06)] bg-white p-1">
          {filters.map((item) => (
            <button
              key={item.id}
              onClick={() => setFilter(item.id)}
              className={`rounded-lg px-3 py-1.5 text-xs capitalize transition-all ${
                filter === item.id ? "bg-[#0f0f17] text-white" : "text-[#71717a] hover:text-[#0f0f17]"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-48 animate-pulse rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white" />
          ))}
        </div>
      ) : visible.length ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {visible.map((item) => (
            <PackageCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={SlidersHorizontal}
          title="No packages match your search"
          description="Try a different filter, or submit a role to create your first package."
        />
      )}
    </PageShell>
  );
}

function PackageCard({ item }: { item: AnalysisSummary }) {
  const status = item.partial ? "Partial" : item.evaluate_only ? "Review ready" : "Complete";
  const statusTone: StatusTone = item.partial ? "warning" : item.evaluate_only ? "info" : "success";
  const matchStatus =
    item.match_score == null
      ? "Submitted"
      : item.match_score >= 80
        ? "Strong match"
        : item.match_score >= 60
          ? "Promising fit"
          : "Needs review";

  return (
    <Link
      to={`/results/${item.id}`}
      className="group rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5 transition-all hover:border-[rgba(0,0,0,0.1)] hover:shadow-md"
    >
      <div className="mb-4 flex items-start gap-4">
        <ScoreRing score={item.match_score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm leading-tight text-[#0f0f17]">{item.role_type ?? "Submitted role"}</h3>
            <StatusPill tone={statusTone}>{status}</StatusPill>
          </div>
          <div className="mt-1 flex items-center gap-1.5">
            {item.company && <span className="text-xs text-[#71717a]">{item.company}</span>}
            {item.company && <span className="text-[#d4d4d8]">·</span>}
            <span className="flex items-center gap-1 font-mono text-xs text-[#9898a8]">
              <Clock className="size-2.5" />
              {new Date(item.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
        <ArrowRight className="mt-1 size-3.5 text-[#d4d4d8] transition-all group-hover:translate-x-0.5 group-hover:text-[#5b5bd6]" />
      </div>

      <p className="line-clamp-2 text-sm leading-6 text-[#71717a]">{item.jd_text}</p>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[rgba(0,0,0,0.04)] pt-3">
        <StatusPill tone={item.match_score == null ? "neutral" : item.match_score >= 80 ? "success" : item.match_score >= 60 ? "info" : "warning"}>
          {matchStatus}
        </StatusPill>
        {item.profile_stale && <StatusPill tone="warning">Profile changed</StatusPill>}
        <span className="ml-auto text-xs text-[#5b5bd6]">Open package</span>
      </div>
    </Link>
  );
}
