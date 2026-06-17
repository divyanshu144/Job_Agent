import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ClipboardCopy, FileSearch, Search } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, PageHeader, PageShell, Panel, StatusPill } from "../components/portal";
import type { StatusTone } from "../components/portal";
import type { AnalysisSummary } from "../types";

type Filter = "all" | "strong" | "documents" | "needs_work" | "partial";

const filters: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "strong", label: "Strong matches" },
  { id: "documents", label: "Documents ready" },
  { id: "needs_work", label: "Needs work" },
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
        (filter === "strong" && (item.match_score ?? 0) >= 80) ||
        (filter === "documents" && !item.evaluate_only && !item.partial) ||
        (filter === "needs_work" && (item.match_score ?? 100) < 70) ||
        (filter === "partial" && item.partial);
      return matchesQuery && matchesFilter;
    });
  }, [filter, items, query]);

  return (
    <PageShell>
      <PageHeader
        title="Application packages"
        description="Review submitted roles, match reviews, prepared documents, and recommendations."
        actions={
          <Link
            to="/analyse"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
          >
            <FileSearch className="size-4" />
            Submit a role
          </Link>
        }
      />

      <Panel>
        <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-600" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search role, company, or package text"
              className="w-full rounded-xl border border-zinc-200 bg-white py-2.5 pl-10 pr-3 text-sm text-zinc-950 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600/25"
            />
          </label>
          <div className="flex gap-2 overflow-x-auto">
            {filters.map((item) => (
              <button
                key={item.id}
                onClick={() => setFilter(item.id)}
                className={`shrink-0 rounded-xl border px-3 py-2 text-sm font-medium transition-colors ${
                  filter === item.id
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : "border-zinc-200 text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </Panel>

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-40 animate-pulse rounded-3xl border border-zinc-200 bg-white" />
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
          icon={ClipboardCopy}
          title="No matching packages"
          description="Try a different filter, or submit a role to create your first package."
        />
      )}
    </PageShell>
  );
}

function PackageCard({ item }: { item: AnalysisSummary }) {
  const status = item.partial
    ? "Partial package"
    : item.evaluate_only
      ? "Match review ready"
      : "Documents ready";
  const statusTone: StatusTone = item.partial
    ? "warning"
    : item.evaluate_only
      ? "neutral"
      : "success";
  const matchStatus =
    item.match_score == null
      ? "Submitted"
      : item.match_score >= 80
        ? "Strong match"
        : item.match_score >= 60
          ? "Promising fit"
          : "Needs review";

  return (
    <div className="rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm transition-colors hover:border-blue-200">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-base font-semibold text-zinc-950">
            {item.role_type ?? "Submitted role"}
            {item.company ? <span className="font-normal text-zinc-500"> at {item.company}</span> : null}
          </p>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-zinc-500">{item.jd_text}</p>
        </div>
        <div className="shrink-0 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-right">
          <p className="text-2xl font-semibold text-zinc-950">{item.match_score ?? "--"}</p>
          <p className="text-xs text-zinc-600">{item.match_score == null ? "pending" : "score"}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <StatusPill tone={item.match_score == null ? "neutral" : item.match_score >= 80 ? "success" : item.match_score >= 60 ? "warning" : "neutral"}>
          {matchStatus}
        </StatusPill>
        <StatusPill tone={statusTone}>{status}</StatusPill>
        <span className="text-xs text-zinc-500">Submitted {new Date(item.created_at).toLocaleString()}</span>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Link
          to={`/results/${item.id}`}
          className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Open package
          <ArrowRight className="size-4" />
        </Link>
        <Link
          to={`/results/${item.id}`}
          className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 px-3.5 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          View recommendations
        </Link>
      </div>
    </div>
  );
}
