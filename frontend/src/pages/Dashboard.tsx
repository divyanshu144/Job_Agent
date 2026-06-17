import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Clock, Download, Sparkles, TrendingUp, UserRound, Zap } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, PageShell, Panel, StatusPill } from "../components/portal";
import { ScoreRing } from "../components/ScoreRing";
import type { StatusTone } from "../components/portal";
import { useAuth } from "../context/AuthContext";
import type { AnalysisSummary } from "../types";

export function Dashboard() {
  const { user } = useAuth();
  const [history, setHistory] = useState<AnalysisSummary[]>([]);

  useEffect(() => {
    api.listHistory().then((items) => setHistory(items.slice(0, 5))).catch(() => {});
  }, []);

  const latest = history[0];
  const documentsReady = history.filter((item) => !item.evaluate_only && !item.partial).length;
  const scores = history
    .map((item) => item.match_score)
    .filter((score): score is number => typeof score === "number");
  const avgScore = scores.length
    ? Math.round(scores.reduce((total, score) => total + score, 0) / scores.length)
    : null;
  const recommendedStep = useMemo(() => {
    if (!history.length) {
      return { title: "Submit your first role", to: "/analyse" };
    }
    if (latest?.evaluate_only) {
      return { title: "Complete latest package", to: `/results/${latest.id}` };
    }
    return { title: "Review prepared work", to: latest ? `/results/${latest.id}` : "/results" };
  }, [history.length, latest]);

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">
            Workspace
          </p>
          <h1 className="text-2xl font-medium leading-tight tracking-[-0.03em] text-[#0f0f17]">
            Your application workspace
          </h1>
          <p className="mt-1 text-sm text-[#71717a]">
            Submit roles, review fit, and receive tailored application packages.
          </p>
          <p className="mt-1 text-xs text-[#9898a8]">Signed in as {user?.email}</p>
        </div>
        <Link
          to="/analyse"
          className="hidden items-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28] sm:flex"
        >
          <Zap className="size-3.5" />
          New Package
        </Link>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Total Packages" value={String(history.length)} sub="Saved workspace items" icon="PK" trend={history.length > 0} />
        <StatCard label="Avg Match Score" value={avgScore == null ? "--" : String(avgScore)} suffix={avgScore == null ? "" : "%"} sub={scores.length ? "Across recent packages" : "No scores yet"} icon="MS" trend={scores.length > 0} />
        <StatCard label="Documents Ready" value={String(documentsReady)} sub="Prepared materials" icon="DR" />
        <StatCard label="Next Step" value={history.length ? "Review" : "Submit"} sub={recommendedStep.title} icon="NS" />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
        <div className="overflow-hidden rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white">
          <div className="flex items-center justify-between border-b border-[rgba(0,0,0,0.05)] px-5 py-4">
            <div>
              <h2 className="text-sm font-medium text-[#0f0f17]">Recent Packages</h2>
              <p className="mt-0.5 text-xs text-[#71717a]">Your last application packages</p>
            </div>
            <Link to="/results" className="flex items-center gap-1 text-xs text-[#5b5bd6] transition-colors hover:text-[#4a4ab8]">
              View all
              <ArrowRight className="size-3" />
            </Link>
          </div>

          {history.length ? (
            <div className="divide-y divide-[rgba(0,0,0,0.04)]">
              {history.map((item) => (
                <Link
                  key={item.id}
                  to={`/results/${item.id}`}
                  className="group flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-[#fafafa]"
                >
                  <ScoreRing score={item.match_score} size={44} strokeWidth={4} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-[#0f0f17]">{item.role_type ?? "Submitted role"}</p>
                    <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-[#71717a]">
                      {item.company ? <span>{item.company}</span> : null}
                      {item.company ? <span className="text-[#d4d4d8]">·</span> : null}
                      <Clock className="size-2.5" />
                      {new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>
                  <PackageStatus item={item} />
                  <ArrowRight className="size-3.5 text-[#d4d4d8] transition-all group-hover:translate-x-0.5 group-hover:text-[#5b5bd6]" />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No submissions yet"
              description="Submit a job description to receive your first match review."
            />
          )}
        </div>

        <Panel>
          <div className="mb-4">
            <h2 className="text-sm font-medium text-[#0f0f17]">Quick Actions</h2>
            <p className="mt-0.5 text-xs text-[#71717a]">Next recommended steps</p>
          </div>
          <div className="space-y-2">
            <QuickAction to="/analyse" icon={<Sparkles className="size-4" />} title="Submit a new role" desc="Start a new application package" primary />
            <QuickAction to="/profile" icon={<UserRound className="size-4" />} title="Update your profile" desc="Improve future tailoring" />
            <QuickAction to={latest ? `/results/${latest.id}` : "/results"} icon={<Download className="size-4" />} title="Review prepared work" desc="Open your latest package" />
          </div>
        </Panel>
      </section>
    </PageShell>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon,
  suffix = "",
  trend = false,
}: {
  label: string;
  value: string;
  sub: string;
  icon: string;
  suffix?: string;
  trend?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-4 transition-shadow hover:shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-xs text-[#9898a8]">{icon}</span>
        {trend && <TrendingUp className="size-3.5 text-emerald-500" />}
      </div>
      <div className="font-mono text-2xl leading-none tracking-tight text-[#0f0f17]">
        {value}
        {suffix && <span className="text-sm text-[#71717a]">{suffix}</span>}
      </div>
      <div className="mt-1 text-xs leading-tight text-[#71717a]">{label}</div>
      <div className="mt-1 font-mono text-[11px] text-[#9898a8]">{sub}</div>
    </div>
  );
}

function QuickAction({
  to,
  icon,
  title,
  desc,
  primary = false,
}: {
  to: string;
  icon: ReactNode;
  title: string;
  desc: string;
  primary?: boolean;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-3 rounded-xl border border-[rgba(0,0,0,0.05)] p-3 text-left transition-all hover:border-[rgba(0,0,0,0.1)] hover:shadow-sm"
    >
      <span className={`flex size-8 items-center justify-center rounded-lg text-sm ${primary ? "bg-[#0f0f17] text-white" : "bg-[#ededf8] text-[#5b5bd6]"}`}>
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm leading-tight text-[#0f0f17]">{title}</div>
        <div className="mt-0.5 text-xs text-[#71717a]">{desc}</div>
      </div>
      <ArrowRight className="size-3.5 text-[#d4d4d8] transition-colors group-hover:text-[#0f0f17]" />
    </Link>
  );
}

function PackageStatus({ item }: { item: AnalysisSummary }) {
  const label = item.partial ? "Partial" : item.evaluate_only ? "Match review" : "Ready";
  const tone: StatusTone = item.partial ? "warning" : item.evaluate_only ? "info" : "success";
  return <StatusPill tone={tone}>{label}</StatusPill>;
}
