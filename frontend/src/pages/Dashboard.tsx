import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileSearch,
  FolderCheck,
  ListChecks,
  UserRound,
} from "lucide-react";
import { api } from "../api/client";
import { EmptyState, PageHeader, PageShell, Panel, SectionHeader, StatusPill } from "../components/portal";
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
  const recommendedStep = useMemo(() => {
    if (!history.length) {
      return {
        title: "Submit your first role",
        body: "Paste a job description so we can prepare your first match review and application package.",
        to: "/analyse",
        label: "Submit a role",
      };
    }
    if (latest?.evaluate_only) {
      return {
        title: "Complete the latest package",
        body: "Your match review is ready. Prepare documents when you are ready to apply.",
        to: `/results/${latest.id}`,
        label: "Open package",
      };
    }
    return {
      title: "Review prepared documents",
      body: "Check the latest cover letter and resume bullets before using them for an application.",
      to: latest ? `/results/${latest.id}` : "/results",
      label: "Review package",
    };
  }, [history.length, latest]);

  return (
    <PageShell>
      <PageHeader
        title="Your application workspace"
        description="Submit roles, review your fit, and receive tailored application materials prepared for each opportunity."
        actions={
          <>
            <Link
              to="/analyse"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
            >
              <FileSearch className="size-4" />
              Submit a role
            </Link>
            <Link
              to="/profile"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white px-5 py-3 text-sm font-semibold text-zinc-800 transition-colors hover:bg-zinc-50"
            >
              <UserRound className="size-4" />
              Review profile
            </Link>
          </>
        }
      />
      <p className="-mt-3 px-1 text-sm text-zinc-500">
        Signed in as <span className="text-zinc-800">{user?.email}</span>
      </p>

      <section className="grid gap-4 lg:grid-cols-4">
        <WorkspaceCard
          title="Latest application package"
          value={latest?.role_type ?? "No package yet"}
          detail={latest?.company ? `For ${latest.company}` : "Submit a role to begin."}
          icon={FolderCheck}
          to={latest ? `/results/${latest.id}` : "/analyse"}
        />
        <WorkspaceCard
          title="Documents ready"
          value={String(documentsReady)}
          detail="Packages with prepared documents"
          icon={FileCheck2}
          to="/results"
        />
        <WorkspaceCard
          title="Profile readiness"
          value="Review"
          detail="Keep your profile current for better tailoring"
          icon={UserRound}
          to="/profile"
        />
        <WorkspaceCard
          title="Recommended next step"
          value={recommendedStep.title}
          detail={recommendedStep.body}
          icon={ListChecks}
          to={recommendedStep.to}
          cta={recommendedStep.label}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.4fr_0.6fr]">
        <Panel>
          <SectionHeader
            title="Recent submissions"
            description="Roles recently submitted for review"
            action={
            <Link to="/results" className="text-sm font-medium text-blue-700 hover:text-blue-600">
              View packages
            </Link>
            }
          />
          {history.length ? (
            <div className="divide-y divide-zinc-100">
              {history.map((item) => (
                <Link
                  key={item.id}
                  to={`/results/${item.id}`}
                  className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-zinc-950">
                      {item.role_type ?? "Submitted role"}
                      {item.company ? <span className="font-normal text-zinc-500"> at {item.company}</span> : null}
                    </p>
                    <p className="mt-1 truncate text-xs text-zinc-500">
                      {new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>
                  <PackageStatus item={item} />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={FolderCheck}
              title="No submissions yet"
              description="Submit a job description to receive your first match review."
            />
          )}
        </Panel>

        <Panel>
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-emerald-600/15 text-emerald-400">
              <CheckCircle2 className="size-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-950">What JobFit prepares</h3>
              <p className="mt-1 text-sm text-zinc-500">Client deliverables</p>
            </div>
          </div>
          <div className="mt-5 space-y-3 text-sm text-zinc-700">
            {["Match review", "Skill-gap recommendations", "Cover letter", "Resume bullets"].map((label) => (
              <div key={label} className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-emerald-500" />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </Panel>
      </section>
    </PageShell>
  );
}

function WorkspaceCard({
  title,
  value,
  detail,
  icon: Icon,
  to,
  cta = "Open",
}: {
  title: string;
  value: string;
  detail: string;
  icon: typeof FolderCheck;
  to: string;
  cta?: string;
}) {
  return (
    <Link
      to={to}
      className="group flex min-h-44 flex-col justify-between rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50/30"
    >
      <div>
        <div className="flex size-10 items-center justify-center rounded-xl border border-zinc-200 bg-zinc-50 text-zinc-700">
          <Icon className="size-5" />
        </div>
        <p className="mt-5 text-xs font-medium uppercase tracking-[0.16em] text-zinc-500">{title}</p>
        <p className="mt-2 line-clamp-2 text-lg font-semibold text-zinc-950">{value}</p>
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-zinc-500">{detail}</p>
      </div>
      <span className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-blue-700">
        {cta}
        <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
      </span>
    </Link>
  );
}

function PackageStatus({ item }: { item: AnalysisSummary }) {
  const label = item.partial ? "Partial" : item.evaluate_only ? "Match review" : "Documents ready";
  const tone: StatusTone = item.partial
    ? "warning"
    : item.evaluate_only
      ? "neutral"
      : "success";

  return (
    <StatusPill tone={tone}>{label}</StatusPill>
  );
}
