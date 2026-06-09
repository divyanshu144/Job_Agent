import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { api, streamGenerate } from "../api/client";
import type { AnalysisDetail, AgentName, AgentStatus, Contact } from "../types";
import { PHASE2_AGENTS } from "../types";
import { ScoreCard } from "../components/ScoreCard";
import { GapList } from "../components/GapList";
import { ResourcePanel } from "../components/ResourcePanel";
import { DocViewer } from "../components/DocViewer";
import { useAuth } from "../context/AuthContext";

type Tab = "score" | "gaps" | "resources" | "letter" | "resume" | "cold_email";
const TABS: { id: Tab; label: string }[] = [
  { id: "score", label: "Score" },
  { id: "gaps", label: "Gaps" },
  { id: "resources", label: "Resources" },
  { id: "letter", label: "Cover Letter" },
  { id: "resume", label: "Resume" },
  { id: "cold_email", label: "Cold Email" },
];

export function Results() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [tab, setTab] = useState<Tab>("score");
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<number | null>(null);
  const [genStates, setGenStates] = useState<Partial<Record<AgentName, AgentStatus>>>({});
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
    setGenStates(Object.fromEntries(PHASE2_AGENTS.map((a) => [a, "pending"])));
    cancelRef.current = streamGenerate(data.id, {
      onAgentStart: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: () => {
        api.getAnalysis(data.id).then(setData).finally(() => setGenerating(false));
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
      const blob = await api.downloadResumeDocx(data.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jobfit-resume-${data.id}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    }
  };

  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!data) return <p className="p-6 text-slate-500">Loading…</p>;
  const r = data.results;
  const tabs = user?.is_admin ? TABS : TABS.filter((t) => t.id !== "cold_email");

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Results</h1>
        <div className="flex items-center gap-2 text-sm">
          {feedbackRating === null ? (
            <>
              <span className="text-slate-400">Helpful?</span>
              <button
                onClick={() => sendFeedback(1)}
                aria-label="Thumbs up"
                className="px-2 py-1 rounded hover:bg-slate-100"
              >
                👍
              </button>
              <button
                onClick={() => sendFeedback(-1)}
                aria-label="Thumbs down"
                className="px-2 py-1 rounded hover:bg-slate-100"
              >
                👎
              </button>
            </>
          ) : (
            <span className="text-slate-400">Thanks for the feedback!</span>
          )}
        </div>
      </div>
      {data.partial && (
        <p className="text-amber-600 text-sm">⚠ Partial results — some agents failed.</p>
      )}

      {data.evaluate_only && !generating && (
        <div className="flex items-center gap-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-800 flex-1">
            Evaluation complete. Generate your cover letter, resource plan, and tailored resume.
          </p>
          <button
            onClick={generate}
            className="shrink-0 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
          >
            Generate Documents
          </button>
        </div>
      )}

      {generating && (
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <p className="text-sm text-slate-600 mb-2">Generating documents…</p>
          <div className="flex gap-3 text-xs text-slate-500">
            {PHASE2_AGENTS.map((a) => (
              <span
                key={a}
                className={
                  genStates[a] === "done"
                    ? "text-green-600"
                    : genStates[a] === "running"
                    ? "text-blue-600"
                    : ""
                }
              >
                {a.replace("_", " ")} {genStates[a] === "done" ? "✓" : genStates[a] === "running" ? "…" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 border-b">
        {tabs
          .filter((t) => t.id !== "cold_email" || !!r.job_parser?.company)
          .map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t.label}{t.id === "cold_email" && coldEmailScreen === "sent" ? " ✓" : ""}
            </button>
          ))}
      </div>

      <div className="pt-2">
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
            : <p className="text-sm text-slate-400 italic">Generate documents to see resource plan.</p>
        )}
        {tab === "letter" && (
          r.cover_letter
            ? <DocViewer title="Cover Letter" content={r.cover_letter.body} filename="cover_letter.txt" />
            : <p className="text-sm text-slate-400 italic">Generate documents to see cover letter.</p>
        )}
        {tab === "resume" && (
          r.resume_tailorer
            ? (
              <div className="space-y-5 text-sm">
                <div className="flex justify-end">
                  <button
                    onClick={downloadResume}
                    className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-700"
                  >
                    Download DOCX
                  </button>
                </div>

                {(r.resume_tailorer.omitted_items ?? []).length > 0 && (
                  <div className="border border-amber-200 bg-amber-50 rounded-lg p-3 space-y-1">
                    {(r.resume_tailorer.omitted_items ?? []).map((item, i) => (
                      <p key={i} className="text-amber-800">
                        Omitted {item.value} because it was {item.reason}.
                      </p>
                    ))}
                  </div>
                )}

                {r.resume_tailorer.headline && (
                  <h2 className="text-lg font-semibold text-slate-900">{r.resume_tailorer.headline}</h2>
                )}
                {r.resume_tailorer.summary && (
                  <section>
                    <h3 className="text-xs font-semibold text-slate-500 uppercase mb-1">Summary</h3>
                    <p className="text-slate-700 whitespace-pre-wrap">{r.resume_tailorer.summary}</p>
                  </section>
                )}
                {(r.resume_tailorer.skills ?? []).length > 0 && (
                  <section>
                    <h3 className="text-xs font-semibold text-slate-500 uppercase mb-1">Skills</h3>
                    <p className="text-slate-700">{(r.resume_tailorer.skills ?? []).join(", ")}</p>
                  </section>
                )}
                {(r.resume_tailorer.experience ?? []).length > 0 && (
                  <section className="space-y-3">
                    <h3 className="text-xs font-semibold text-slate-500 uppercase">Experience</h3>
                    {(r.resume_tailorer.experience ?? []).map((item, i) => (
                      <div key={i} className="space-y-1">
                        <p className="font-medium text-slate-900">
                          {[item.role, item.company].filter(Boolean).join(" - ")}
                          {item.dates ? ` (${item.dates})` : ""}
                        </p>
                        <ul className="list-disc pl-5 space-y-1 text-slate-700">
                          {(item.bullets ?? []).map((bullet, j) => <li key={j}>{bullet}</li>)}
                        </ul>
                      </div>
                    ))}
                  </section>
                )}
                {(r.resume_tailorer.tailored_bullets ?? []).length > 0 && (
                  <section className="space-y-3">
                    <h3 className="text-xs font-semibold text-slate-500 uppercase">Bullet Rewrites</h3>
                    {(r.resume_tailorer.tailored_bullets ?? []).map((b, i) => (
                      <div key={i} className="border rounded-lg p-4 space-y-2">
                        <p className="text-slate-400 line-through">{b.original}</p>
                        <p className="text-slate-900 font-medium">{b.rewritten}</p>
                        <p className="text-xs text-slate-400 italic">{b.rationale}</p>
                      </div>
                    ))}
                  </section>
                )}
              </div>
            )
            : <p className="text-sm text-slate-400 italic">Generate documents to see tailored resume.</p>
        )}

        {tab === "cold_email" && (
          <div className="space-y-4">
            {contactsError && (
              <p className="text-sm text-red-600">{contactsError}</p>
            )}
            {contactsLoading && (
              <p className="text-sm text-slate-400">Loading…</p>
            )}

            {/* Screen 1 — Contact Picker */}
            {!contactsLoading && coldEmailScreen === "picker" && (
              <div className="space-y-4">
                {contacts.length === 0 ? (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-500">
                      No contacts discovered yet. Enter a company domain to search:
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="stripe.com"
                        value={domainOverride}
                        onChange={(e) => setDomainOverride(e.target.value)}
                        className="flex-1 border rounded px-3 py-2 text-sm"
                      />
                      <button
                        onClick={() => handleDiscover(domainOverride)}
                        className="px-4 py-2 bg-blue-600 text-white rounded text-sm"
                      >
                        Search
                      </button>
                    </div>
                    <button
                      onClick={() => handleDiscover()}
                      className="text-sm text-blue-600 underline"
                    >
                      Auto-detect from job description
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-600 font-medium">
                      Select a contact to email:
                    </p>
                    {contacts.map((c) => {
                      const badge =
                        c.confidence >= 0.8
                          ? { label: "High", cls: "bg-green-100 text-green-700" }
                          : c.confidence >= 0.5
                          ? { label: "Medium", cls: "bg-yellow-100 text-yellow-700" }
                          : { label: "Low", cls: "bg-slate-100 text-slate-600" };
                      return (
                        <label
                          key={c.id}
                          className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer ${
                            selectedContactId === c.id ? "border-blue-500 bg-blue-50" : ""
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
                            <p className="text-sm font-medium">{c.name ?? c.email}</p>
                            {c.title && (
                              <p className="text-xs text-slate-500">{c.title}</p>
                            )}
                            <p className="text-xs text-slate-400">{c.email}</p>
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                            {badge.label}
                          </span>
                        </label>
                      );
                    })}
                    <button
                      onClick={handleDraft}
                      disabled={!selectedContactId || drafting}
                      className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
                    >
                      {drafting ? "Drafting…" : "Draft Email"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Screen 2 — Draft Review */}
            {!contactsLoading && coldEmailScreen === "review" && (
              <div className="space-y-3">
                {drafting && (
                  <p className="text-sm text-slate-400">Drafting email (5–15s)…</p>
                )}
                {!drafting && (
                  <>
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Subject</label>
                      <input
                        type="text"
                        value={draftSubject}
                        onChange={(e) => setDraftSubject(e.target.value)}
                        className="w-full border rounded px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Body</label>
                      <textarea
                        value={draftBody}
                        onChange={(e) => setDraftBody(e.target.value)}
                        rows={10}
                        className="w-full border rounded px-3 py-2 text-sm font-mono"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setColdEmailScreen("picker")}
                        className="px-4 py-2 border rounded text-sm text-slate-500 hover:bg-slate-50"
                      >
                        ← Change contact
                      </button>
                      <button
                        onClick={() => {
                          if (draftBody !== originalDraftBody) {
                            if (!window.confirm("This will overwrite your edits. Continue?")) return;
                          }
                          handleDraft();
                        }}
                        className="px-4 py-2 border rounded text-sm text-slate-700 hover:bg-slate-50"
                      >
                        Re-draft
                      </button>
                      <button
                        onClick={() => setShowSendModal(true)}
                        disabled={sending}
                        className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
                      >
                        {sending ? "Sending…" : "Send"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Screen 3 — Sent Confirmation */}
            {!contactsLoading && coldEmailScreen === "sent" && (() => {
              const sentContact = contacts.find((c) => c.id === selectedContactId) ?? contacts.find((c) => c.status === "sent");
              return (
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <p className="text-green-800 font-medium text-sm">
                    ✓ Sent to {sentContact?.name ?? sentContact?.email ?? "contact"}
                    {sentContact?.email && sentContact?.name ? ` (${sentContact.email})` : ""}
                  </p>
                  {sentContact?.sent_at && (
                    <p className="text-xs text-green-600 mt-1">
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
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
                  <div className="bg-white rounded-lg p-6 max-w-sm w-full shadow-xl space-y-4">
                    <p className="text-sm text-slate-800">
                      Send to <strong>{target?.email}</strong>? This will send via Gmail. The email
                      lands in Drafts briefly before firing — you can delete it from there if you
                      act fast.
                    </p>
                    <div className="flex gap-3 justify-end">
                      <button
                        onClick={() => setShowSendModal(false)}
                        className="px-4 py-2 text-sm border rounded text-slate-700"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSendConfirm}
                        className="px-4 py-2 text-sm bg-blue-600 text-white rounded"
                      >
                        Confirm Send
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
  );
}
