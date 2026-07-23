import { useState, useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, Download, FileEdit, RefreshCw, ThumbsDown, ThumbsUp, Wand2 } from "lucide-react";
import { api, streamGenerate, retryAnalysis } from "../api/client";
import type { AnalysisDetail, AgentName, AgentStatus, Contact, Step, RetryRequest, ResumeTailorerOutput } from "../types";
import { PHASE2_AGENTS } from "../types";
import { ScoreCard } from "../components/ScoreCard";
import { GapList } from "../components/GapList";
import { ResourcePanel } from "../components/ResourcePanel";
import { DocViewer } from "../components/DocViewer";
import { EmptyState, PageShell, Panel, PrimaryButton, SecondaryButton, StatusPill } from "../components/portal";
import { useAuth } from "../context/AuthContext";

type Tab = "score" | "gaps" | "resources" | "letter" | "resume" | "cold_email" | "trace";
const TABS: { id: Tab; label: string }[] = [
  { id: "score", label: "Match Review" },
  { id: "gaps", label: "Skill Gaps" },
  { id: "resources", label: "Recommendations" },
  { id: "letter", label: "Cover Letter" },
  { id: "resume", label: "Resume" },
  { id: "cold_email", label: "Outreach" },
  { id: "trace", label: "Technical Trace" },
];

const STEP_LABELS: Record<string, string> = {
  job_parser: "Reviewing role requirements",
  match_scorer: "Comparing against your profile",
  gap_analyst: "Identifying gaps",
  resource_planner: "Preparing recommendations",
  cover_letter: "Drafting documents",
  resume_tailorer: "Finalising package",
};

const TECH_STEP_LABELS: Record<string, string> = {
  job_parser: "job_parser",
  match_scorer: "match_scorer",
  gap_analyst: "gap_analyst",
  resource_planner: "resource_planner",
  cover_letter: "cover_letter",
  resume_tailorer: "resume_tailorer",
};

function stepIndicator(status: string): { icon: string; cls: string } {
  switch (status) {
    case "success":
    case "done":
      return { icon: "✓", cls: "text-emerald-700" };
    case "error":
      return { icon: "!", cls: "text-rose-700" };
    case "running":
      return { icon: "...", cls: "text-blue-700" };
    default:
      return { icon: "-", cls: "text-zinc-500" };
  }
}

export function Results() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [tab, setTab] = useState<Tab>("score");
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<number | null>(null);
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null);
  const [genStates, setGenStates] = useState<Partial<Record<AgentName, AgentStatus>>>({});
  const [genErrors, setGenErrors] = useState<Partial<Record<AgentName, string>>>({});
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryRunning, setRetryRunning] = useState<Partial<Record<string, AgentStatus>>>({});
  const cancelRef = useRef<(() => void) | null>(null);

  // Cold Email state
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [contactsError, setContactsError] = useState<string | null>(null);
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [originalDraftBody, setOriginalDraftBody] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [showSendModal, setShowSendModal] = useState(false);
  const [coldEmailScreen, setColdEmailScreen] = useState<"picker" | "review" | "sent">("picker");
  const [domainOverride, setDomainOverride] = useState("");

  useEffect(() => {
    if (id) api.getAnalysis(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

  useEffect(() => {
    if (tab !== "cold_email" || !id) return;
    setContactsLoading(true);
    api.getContacts(id)
      .then((cs) => {
        setContacts(cs);
        const sent = cs.find((c) => c.status === "sent");
        const drafted = cs.find((c) => c.status === "drafted");
        if (sent) {
          setColdEmailScreen("sent");
          setSelectedContactId(sent.id);
        } else if (drafted) {
          setColdEmailScreen("review");
          setSelectedContactId(drafted.id);
          setDraftSubject(drafted.draft_subject ?? "");
          setDraftBody(drafted.draft_text ?? "");
          setOriginalDraftBody(drafted.draft_text ?? "");
        } else {
          setColdEmailScreen("picker");
        }
      })
      .catch((e) => setContactsError(String(e)))
      .finally(() => setContactsLoading(false));
  }, [tab, id]);

  const generate = () => {
    if (!data) return;
    setGenerating(true);
    setGenErrors({});
    setGenStates(Object.fromEntries(PHASE2_AGENTS.map((a) => [a, "pending"])));
    cancelRef.current = streamGenerate(data.id, {
      onAgentStart: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent, error }) => {
        setGenStates((p) => ({ ...p, [agent]: "error" }));
        setGenErrors((p) => ({ ...p, [agent]: error }));
      },
      onPipelineDone: () => {
        api.getAnalysis(data.id).then(setData).finally(() => setGenerating(false));
      },
    });
  };

  const runRetry = (agents?: string[]) => {
    if (!data || isRetrying) return;
    setIsRetrying(true);
    setRetryRunning({});
    const body: RetryRequest = agents ? { agents, scope: "failed" } : { scope: "failed" };
    cancelRef.current = retryAnalysis(data.id, body, {
      onAgentStart: ({ agent }) => setRetryRunning((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setRetryRunning((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setRetryRunning((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: () => {
        api.getAnalysis(data.id).then(setData).finally(() => {
          setIsRetrying(false);
          setRetryRunning({});
        });
      },
    });
  };

  const handleDiscover = (domain?: string) => {
    if (!id) return;
    setContactsLoading(true);
    setContactsError(null);
    api.discoverContacts(id, domain || undefined)
      .then((cs) => {
        setSelectedContactId(null);
        setContacts(cs);
        setColdEmailScreen("picker");
      })
      .catch((e) => setContactsError(String(e)))
      .finally(() => setContactsLoading(false));
  };

  const handleDraft = () => {
    if (!selectedContactId) return;
    setDrafting(true);
    api.draftEmail(selectedContactId)
      .then((d) => {
        setDraftSubject(d.subject);
        setDraftBody(d.body);
        setOriginalDraftBody(d.body);
        setColdEmailScreen("review");
      })
      .catch((e) => setContactsError(String(e)))
      .finally(() => setDrafting(false));
  };

  const handleSendConfirm = () => {
    if (!selectedContactId || !id) return;
    setSending(true);
    setShowSendModal(false);
    api.sendEmail(selectedContactId)
      .then(() =>
        api.getContacts(id).then((cs) => {
          setContacts(cs);
          setColdEmailScreen("sent");
        })
      )
      .catch((e) => setContactsError(String(e)))
      .finally(() => setSending(false));
  };

  const sendFeedback = (rating: number) => {
    if (!data) return;
    setFeedbackRating(rating);
    api.submitFeedback(data.id, rating).catch(() => setFeedbackRating(null));
  };

  const downloadResume = async () => {
    if (!data) return;
    try {
      let blob: Blob;
      let extension = "pdf";
      setDownloadNotice(null);
      try {
        blob = await api.downloadResumePdf(data.id);
      } catch {
        // Fall back to DOCX, but say so — a silent format switch masked a
        // 10-day prod PDF outage. The user must know they got a fallback.
        blob = await api.downloadResumeDocx(data.id);
        extension = "docx";
        setDownloadNotice(
          "PDF generation failed, so you got the DOCX version instead. The team can check the server logs for the PDF error.",
        );
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jobfit-resume-${data.id}.${extension}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-3xl rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
        The application package could not be loaded. {error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-7xl space-y-4">
        <div className="h-36 animate-pulse rounded-3xl border border-zinc-200 bg-white" />
        <div className="h-96 animate-pulse rounded-3xl border border-zinc-200 bg-white" />
      </div>
    );
  }
  const r = data.results;
  const steps: Step[] = data.steps ?? [];
  const effectiveStatus = (s: Step): string => retryRunning[s.name] ?? s.status;
  const tabs = user?.is_admin ? TABS : TABS.filter((t) => t.id !== "cold_email" && t.id !== "trace");
  const score = r.match_scorer?.score;
  const role = r.job_parser?.role_type ?? "Submitted role";
  const company = r.job_parser?.company;
  const matchLabel =
    typeof score === "number"
      ? score >= 80
        ? "Strong match"
        : score >= 60
          ? "Promising fit"
          : "Needs work"
      : "Evaluation ready";

  return (
    <PageShell width="medium">
      <Panel className="overflow-hidden p-6 sm:p-7">
        <div className="flex flex-col items-start justify-between gap-5 lg:flex-row lg:items-center">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">Application package</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-950">
              {role}{company ? <span className="font-normal text-zinc-400"> at {company}</span> : null}
            </h2>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-medium">
              <StatusPill tone="info">{matchLabel}</StatusPill>
              <StatusPill tone="neutral">
                {data.evaluate_only ? "Match review ready" : "Documents ready"}
              </StatusPill>
              {data.partial && (
                <StatusPill tone="warning">
                  <AlertTriangle className="size-3.5" />
                  Partial package
                </StatusPill>
              )}
            </div>
          </div>
        <div className="flex items-center gap-2 text-sm">
          {feedbackRating === null ? (
            <>
              <span className="text-zinc-500">Helpful?</span>
              <button
                onClick={() => sendFeedback(1)}
                aria-label="Thumbs up"
                className="rounded-lg border border-zinc-200 p-2 text-zinc-500 transition-colors hover:bg-zinc-50 hover:text-emerald-700"
              >
                <ThumbsUp className="size-4" />
              </button>
              <button
                onClick={() => sendFeedback(-1)}
                aria-label="Thumbs down"
                className="rounded-lg border border-zinc-200 p-2 text-zinc-500 transition-colors hover:bg-zinc-50 hover:text-rose-700"
              >
                <ThumbsDown className="size-4" />
              </button>
            </>
          ) : (
            <span className="text-zinc-400">Thanks for the feedback!</span>
          )}
        </div>
        </div>
      </Panel>

      {steps.length > 0 && (
        <Panel className="text-xs text-zinc-500">
          <div className="flex flex-col items-start justify-between gap-2 sm:flex-row sm:items-center">
            <span className="font-semibold uppercase tracking-[0.16em] text-zinc-500">Review progress</span>
            {data.partial && (
              <SecondaryButton
                onClick={() => runRetry()}
                disabled={isRetrying}
                className="px-3 py-2 text-xs"
              >
                <RefreshCw className={`size-3.5 ${isRetrying ? "animate-spin" : ""}`} />
                Retry all failed
              </SecondaryButton>
            )}
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-3 xl:grid-cols-6">
            {steps.map((s, i) => {
              const status = effectiveStatus(s);
              const ind = stepIndicator(status);
              return (
                <span
                  key={`${s.name}-${i}`}
                  className="rounded-2xl border border-zinc-200 bg-zinc-50 px-3 py-2.5"
                  title={status === "error" ? s.message ?? "" : undefined}
                >
                  <span className={`mb-1 block text-sm ${ind.cls}`}>{ind.icon}</span>
                  <span className="block leading-5">{STEP_LABELS[s.name] ?? s.name}</span>
                  <span className="mt-1 block text-[11px] capitalize text-zinc-500">{status}</span>
                  {status === "error" && (
                    <button
                      onClick={() => runRetry([s.name])}
                      disabled={isRetrying}
                      className="mt-1 text-blue-700 underline disabled:opacity-50"
                    >
                      retry
                    </button>
                  )}
                </span>
              );
            })}
          </div>
        </Panel>
      )}

      {data.evaluate_only && !generating && (
        <Panel className="flex flex-col items-start gap-4 border-blue-200 bg-blue-50 sm:flex-row sm:items-center">
          <p className="flex-1 text-sm leading-6 text-blue-950">
            Match review complete. Prepare your cover letter, recommendations, and tailored resume bullets.
          </p>
          <PrimaryButton
            onClick={generate}
            className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 sm:w-auto"
          >
            <Wand2 className="size-4" />
            Prepare documents
          </PrimaryButton>
        </Panel>
      )}

      {generating && (
        <Panel>
          <p className="mb-3 text-sm text-zinc-700">Preparing documents...</p>
          <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
            {PHASE2_AGENTS.map((a) => (
              <span
                key={a}
                className={
                  genStates[a] === "done"
                    ? "text-emerald-700"
                    : genStates[a] === "running"
                    ? "text-blue-700"
                    : ""
                }
              >
                {STEP_LABELS[a]} {genStates[a] === "done" ? "✓" : genStates[a] === "running" ? "..." : ""}
              </span>
            ))}
          </div>
          {Object.entries(genErrors).length > 0 && (
            <div className="mt-3 space-y-1">
              {Object.entries(genErrors).map(([agent, message]) => (
                <p key={agent} className="text-xs text-rose-400">
                  {STEP_LABELS[agent] ?? "Package step"} failed: {message}
                </p>
              ))}
            </div>
          )}
        </Panel>
      )}

      <div className="overflow-hidden rounded-3xl border border-zinc-200 bg-white shadow-sm">
        <div className="flex gap-1 overflow-x-auto border-b border-zinc-200 bg-zinc-50 px-3 pt-3">
        {tabs
          .filter((t) => t.id !== "cold_email" || !!r.job_parser?.company)
          .map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`shrink-0 rounded-t-xl border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                tab === t.id
                  ? "border-blue-600 bg-white text-blue-700"
                  : "border-transparent text-zinc-500 hover:text-zinc-900"
              }`}
            >
              {t.label}{t.id === "cold_email" && coldEmailScreen === "sent" ? " ✓" : ""}
            </button>
          ))}
      </div>

      <div className="p-4 sm:p-5">
        {tab === "score" && r.match_scorer && (
          <ScoreCard
            score={r.match_scorer.score}
            matched={r.match_scorer.matched_skills}
            missing={r.match_scorer.missing_skills}
            partial={r.match_scorer.partial_matches}
          />
        )}
        {tab === "gaps" && r.gap_analyst && (
          <GapList
            critical={r.gap_analyst.critical_gaps}
            niceToHave={r.gap_analyst.nice_to_have_gaps}
          />
        )}
        {tab === "resources" && (
          r.resource_planner
            ? <ResourcePanel gaps={r.resource_planner.gaps} />
            : <EmptyPanel>Prepare documents to see recommendations.</EmptyPanel>
        )}
        {tab === "letter" && (
          r.cover_letter
            ? <DocViewer title="Cover Letter" content={r.cover_letter.body} filename="cover_letter.txt" />
            : <EmptyPanel>Prepare documents to see the cover letter.</EmptyPanel>
        )}
        {tab === "resume" && (
          r.resume_tailorer
            ? (
              <div className="space-y-3">
                {downloadNotice && (
                  <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    {downloadNotice}
                  </p>
                )}
                <Link
                  to={`/resume/analysis/${data.id}`}
                  className="inline-flex items-center gap-2 rounded bg-[#5b5bd6] px-4 py-2 text-sm font-medium text-white hover:bg-[#6b6be0]"
                >
                  <FileEdit className="size-4" /> Edit this resume
                </Link>
                <ResumeDownloadPreview resume={r.resume_tailorer} onDownload={downloadResume} />
              </div>
            )
            : <EmptyPanel>Prepare documents to see tailored resume bullets.</EmptyPanel>
        )}

        {tab === "trace" && user?.is_admin && (
          <div className="space-y-3">
            <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
              <p className="text-sm font-semibold text-zinc-950">Technical Trace</p>
              <p className="mt-1 text-sm text-zinc-500">
                Admin-only execution details for reviewing the underlying workflow.
              </p>
            </div>
            {steps.length ? (
              <div className="overflow-hidden rounded-2xl border border-zinc-200">
                <div className="grid grid-cols-[1.2fr_0.7fr_0.7fr_1.2fr] gap-3 border-b border-zinc-200 bg-zinc-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  <span>Agent</span>
                  <span>Phase</span>
                  <span>Status</span>
                  <span>Message</span>
                </div>
                {steps.map((step) => (
                  <div key={step.name} className="grid grid-cols-[1.2fr_0.7fr_0.7fr_1.2fr] gap-3 border-b border-zinc-200 px-4 py-3 text-sm text-zinc-700 last:border-b-0">
                    <span className="font-mono text-xs text-zinc-400">{TECH_STEP_LABELS[step.name] ?? step.name}</span>
                    <span>{step.phase}</span>
                    <span>{effectiveStatus(step)}</span>
                    <span className="truncate text-zinc-500">{step.message ?? "No message"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel>No technical trace is available for this package.</EmptyPanel>
            )}
          </div>
        )}

        {tab === "cold_email" && (
          <div className="space-y-4">
            {contactsError && (
              <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{contactsError}</p>
            )}
            {contactsLoading && (
              <p className="text-sm text-zinc-500">Loading...</p>
            )}

            {/* Screen 1: Contact Picker */}
            {!contactsLoading && coldEmailScreen === "picker" && (
              <div className="space-y-4">
                {contacts.length === 0 ? (
                  <div className="space-y-3">
                    <p className="text-sm text-zinc-500">
                      No contacts discovered yet. Enter a company domain to search:
                    </p>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        type="text"
                        placeholder="stripe.com"
                        value={domainOverride}
                        onChange={(e) => setDomainOverride(e.target.value)}
                        className="flex-1 rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                      />
                      <button
                        onClick={() => handleDiscover(domainOverride)}
                        className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
                      >
                        Search
                      </button>
                    </div>
                    <button
                      onClick={() => handleDiscover()}
                      className="text-sm font-medium text-blue-700 underline"
                    >
                      Auto-detect from job description
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm font-medium text-zinc-700">
                      Select a contact to email:
                    </p>
                    {contacts.map((c) => {
                      const badge =
                        c.confidence >= 0.8
                          ? { label: "High", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" }
                          : c.confidence >= 0.5
                          ? { label: "Medium", cls: "bg-amber-50 text-amber-700 border-amber-200" }
                          : { label: "Low", cls: "bg-zinc-50 text-zinc-600 border-zinc-200" };
                      return (
                        <label
                          key={c.id}
                          className={`flex cursor-pointer items-center gap-3 rounded-2xl border p-3 ${
                            selectedContactId === c.id ? "border-blue-200 bg-blue-50" : "border-zinc-200 bg-white"
                          }`}
                        >
                          <input
                            type="radio"
                            name="contact"
                            value={c.id}
                            checked={selectedContactId === c.id}
                            onChange={() => setSelectedContactId(c.id)}
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-zinc-950">{c.name ?? c.email}</p>
                            {c.title && (
                              <p className="text-xs text-zinc-500">{c.title}</p>
                            )}
                            <p className="text-xs text-zinc-400">{c.email}</p>
                          </div>
                          <span className={`rounded-lg border px-2 py-0.5 text-xs font-medium ${badge.cls}`}>
                            {badge.label}
                          </span>
                        </label>
                      );
                    })}
                    <button
                      onClick={handleDraft}
                      disabled={!selectedContactId || drafting}
                      className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
                    >
                      {drafting ? "Drafting..." : "Draft email"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Screen 2: Draft Review */}
            {!contactsLoading && coldEmailScreen === "review" && (
              <div className="space-y-3">
                {drafting && (
                  <p className="text-sm text-zinc-500">Drafting email...</p>
                )}
                {!drafting && (
                  <>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-zinc-500">Subject</label>
                      <input
                        type="text"
                        value={draftSubject}
                        onChange={(e) => setDraftSubject(e.target.value)}
                        className="w-full rounded-xl border border-zinc-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-zinc-500">Body</label>
                      <textarea
                        value={draftBody}
                        onChange={(e) => setDraftBody(e.target.value)}
                        rows={10}
                        className="w-full rounded-xl border border-zinc-200 px-3 py-2.5 text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                      />
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <button
                        onClick={() => setColdEmailScreen("picker")}
                        className="rounded-xl border border-zinc-200 px-4 py-2.5 text-sm font-medium text-zinc-600 hover:bg-zinc-50"
                      >
                        Change contact
                      </button>
                      <button
                        onClick={() => {
                          if (draftBody !== originalDraftBody) {
                            if (!window.confirm("This will overwrite your edits. Continue?")) return;
                          }
                          handleDraft();
                        }}
                        className="rounded-xl border border-zinc-200 px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
                      >
                        Re-draft
                      </button>
                      <button
                        onClick={() => setShowSendModal(true)}
                        disabled={sending}
                        className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
                      >
                        {sending ? "Sending..." : "Send"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Screen 3: Sent Confirmation */}
            {!contactsLoading && coldEmailScreen === "sent" && (() => {
              const sentContact = contacts.find((c) => c.id === selectedContactId) ?? contacts.find((c) => c.status === "sent");
              return (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="text-sm font-medium text-emerald-800">
                    ✓ Sent to {sentContact?.name ?? sentContact?.email ?? "contact"}
                    {sentContact?.email && sentContact?.name ? ` (${sentContact.email})` : ""}
                  </p>
                  {sentContact?.sent_at && (
                    <p className="mt-1 text-xs text-emerald-600">
                      {new Date(sentContact.sent_at).toLocaleString()}
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Send confirmation modal */}
            {showSendModal && (() => {
              const target = contacts.find((c) => c.id === selectedContactId);
              return (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/40 p-4">
                  <div className="w-full max-w-sm space-y-4 rounded-3xl bg-white p-6 shadow-xl">
                    <p className="text-sm leading-6 text-zinc-800">
                      Send to <strong>{target?.email}</strong>? This will send via Gmail. The email
                      lands in Drafts briefly before sending. You can delete it from there if you
                      act fast.
                    </p>
                    <div className="flex flex-col justify-end gap-3 sm:flex-row">
                      <button
                        onClick={() => setShowSendModal(false)}
                        className="rounded-xl border border-zinc-200 px-4 py-2.5 text-sm font-medium text-zinc-700"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSendConfirm}
                        className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
                      >
                        Confirm send
                      </button>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
      </div>
      </div>
    </PageShell>
  );
}

function EmptyPanel({ children }: { children: string }) {
  return (
    <EmptyState title={children} />
  );
}

function ResumeDownloadPreview({
  resume,
  onDownload,
}: {
  resume: ResumeTailorerOutput;
  onDownload: () => void;
}) {
  const experienceBulletCount = (resume.experience ?? []).reduce(
    (total, item) => total + (item.bullets ?? []).length,
    0,
  );
  const projectBulletCount = (resume.projects ?? []).reduce(
    (total, item) => total + (item.bullets ?? []).length,
    0,
  );
  const changeItems = [
    resume.headline ? "Headline tailored to the role" : null,
    resume.summary ? "Professional summary rewritten" : null,
    (resume.skills ?? []).length ? `${resume.skills.length} relevant skills selected and ordered` : null,
    (resume.experience ?? []).length
      ? `${resume.experience.length} experience section${resume.experience.length === 1 ? "" : "s"} included`
      : null,
    experienceBulletCount ? `${experienceBulletCount} experience bullet${experienceBulletCount === 1 ? "" : "s"} prepared` : null,
    (resume.projects ?? []).length
      ? `${resume.projects.length} project section${resume.projects.length === 1 ? "" : "s"} included`
      : null,
    projectBulletCount ? `${projectBulletCount} project bullet${projectBulletCount === 1 ? "" : "s"} prepared` : null,
    (resume.education ?? []).length ? "Education section included" : null,
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-5 text-sm">
      <div className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
          <div className="mx-auto max-w-[260px] rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
            <div className="mb-4 text-center">
              <p className="line-clamp-2 text-sm font-semibold text-zinc-950">
                {resume.headline || "Tailored Resume"}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-zinc-400">
                PDF Preview
              </p>
            </div>
            <PreviewSection label="Summary" active={Boolean(resume.summary)} />
            <PreviewSection label="Skills" active={(resume.skills ?? []).length > 0} />
            <PreviewSection label="Experience" active={(resume.experience ?? []).length > 0} />
            <PreviewSection label="Projects" active={(resume.projects ?? []).length > 0} />
            <PreviewSection label="Education" active={(resume.education ?? []).length > 0} />
          </div>
          <button
            onClick={onDownload}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#1a1a28]"
          >
            <Download className="size-4" />
            Download Resume (.pdf)
          </button>
          <p className="mt-3 text-center text-xs leading-5 text-zinc-500">
            The full resume is prepared as a one-page LaTeX PDF.
          </p>
        </div>

        <div className="space-y-4">
          <section className="rounded-2xl border border-zinc-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-zinc-950">What changed</h3>
            {changeItems.length ? (
              <ul className="mt-3 space-y-2 text-zinc-700">
                {changeItems.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-2 size-1.5 rounded-full bg-[#5b5bd6]" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-zinc-500">No resume sections were returned for this package.</p>
            )}
          </section>

          {(resume.tailored_bullets ?? []).length > 0 && (
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">
                Bullet changes
              </h3>
              {(resume.tailored_bullets ?? []).map((b, i) => (
                <div key={i} className="space-y-2 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-zinc-500 line-through">{b.original}</p>
                  <p className="font-medium text-zinc-950">{b.rewritten}</p>
                  <p className="text-xs italic text-zinc-500">{b.rationale}</p>
                </div>
              ))}
            </section>
          )}

          {(resume.omitted_items ?? []).length > 0 && (
            <details className="rounded-xl border border-amber-200 bg-amber-50 p-3">
              <summary className="cursor-pointer text-sm font-medium text-amber-800">
                Resume tailoring notes ({(resume.omitted_items ?? []).length})
              </summary>
              <div className="mt-3 space-y-1">
                {(resume.omitted_items ?? []).map((item, i) => (
                  <p key={i} className="text-amber-700">
                    Omitted {item.value} because it was {item.reason}.
                  </p>
                ))}
              </div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

function PreviewSection({ label, active }: { label: string; active: boolean }) {
  return (
    <div className={`border-t py-2.5 ${active ? "border-zinc-200" : "border-zinc-100 opacity-40"}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
          {label}
        </span>
        <span className={`size-1.5 rounded-full ${active ? "bg-emerald-500" : "bg-zinc-300"}`} />
      </div>
      <div className="space-y-1.5">
        <div className="h-1.5 rounded-full bg-zinc-200" />
        <div className="h-1.5 w-5/6 rounded-full bg-zinc-100" />
        <div className="h-1.5 w-2/3 rounded-full bg-zinc-100" />
      </div>
    </div>
  );
}
