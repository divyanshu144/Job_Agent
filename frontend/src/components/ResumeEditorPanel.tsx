import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Plus, RefreshCw, Send, Sparkles, Undo2 } from "lucide-react";
import { api, ApiError, errorMessage, streamResumeChat } from "../api/client";
import { ResumePreview } from "./ResumePreview";
import { WarningChips } from "./WarningChips";
import { PrimaryButton, SecondaryButton, StatusPill } from "./portal";
import type {
  ResumeDocumentResponse,
  ResumeTailorerOutput,
  ResumeVersionSummary,
  ValidationWarning,
} from "../types";

type ChatLine = { role: "user" | "assistant"; text: string };

const INPUT =
  "w-full rounded-xl border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm text-[#0f0f17] outline-none transition focus:border-[#5b5bd6] focus:ring-2 focus:ring-[rgba(91,91,214,0.15)] disabled:opacity-50";

export function ResumeEditorPanel({ analysisId }: { analysisId?: string }) {
  const isFork = Boolean(analysisId);

  const [doc, setDoc] = useState<ResumeDocumentResponse | null>(null);
  const [versions, setVersions] = useState<ResumeVersionSummary[]>([]);
  const [chatLog, setChatLog] = useState<ChatLine[]>([]);
  const [chatWarnings, setChatWarnings] = useState<ValidationWarning[]>([]);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmPromote, setConfirmPromote] = useState<ValidationWarning[] | null>(null);
  const cancelStream = useRef<(() => void) | null>(null);
  // Guards chat-stream callbacks against a stream started for a document that
  // is no longer loaded (e.g. the user switched/created a version mid-stream).
  const activeDocId = useRef<string | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const d = isFork
        ? await api.getAnalysisResume(analysisId!)
        : await api.getMasterResume();
      setDoc(d);
      setChatWarnings([]); // fresh read is the warnings source of truth
      setError(null);
      if (!isFork) setVersions(await api.listResumeVersions());
    } catch (e) {
      setError(errorMessage(e, "Failed to load resume"));
    }
  }, [analysisId, isFork]);

  useEffect(() => {
    activeDocId.current = doc?.id ?? null;
  }, [doc?.id]);

  useEffect(() => {
    void load();
    return () => cancelStream.current?.();
  }, [load]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [chatLog]);

  const onConflict = useCallback((rev: number, content: ResumeTailorerOutput) => {
    setDoc((d) => (d ? { ...d, rev, content } : d));
    setNotice("Your resume changed elsewhere — reloaded the latest version.");
  }, []);

  const applyInlineEdit = async (mutate: (draft: ResumeTailorerOutput) => void) => {
    if (!doc) return;
    const draft: ResumeTailorerOutput = JSON.parse(JSON.stringify(doc.content));
    mutate(draft);
    try {
      const updated = await api.patchResumeContent(doc.id, doc.rev, draft);
      setDoc(updated);
      setChatWarnings([]);
      setNotice(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        await load();
        setNotice("Your resume changed elsewhere — reloaded; that edit wasn't applied.");
      } else {
        setError(errorMessage(e));
      }
    }
  };

  const sendChat = () => {
    if (!doc || !instruction.trim() || busy) return;
    const text = instruction.trim();
    // Captured so a late event from this stream can be dropped if the user
    // switched to a different document mid-stream.
    const streamDocId = doc.id;
    setInstruction("");
    setBusy(true);
    setChatLog((l) => [...l, { role: "user", text }]);
    cancelStream.current = streamResumeChat(doc.id, doc.rev, text, {
      onEditDone: (r) => {
        if (activeDocId.current !== streamDocId) return;
        setDoc((d) => (d ? { ...d, rev: r.rev, content: r.content } : d));
        setChatWarnings(r.warnings);
        const suffix = r.fallback_used ? " (applied with a backup model)" : "";
        const rule = r.new_rule ? ` · Rule saved: ${r.new_rule.mode} “${r.new_rule.text}”` : "";
        setChatLog((l) => [...l, { role: "assistant", text: `${r.summary}${suffix}${rule}` }]);
      },
      onEditConflict: (c) => {
        if (activeDocId.current !== streamDocId) return;
        onConflict(c.rev, c.content);
      },
      onEditError: (m) => {
        if (activeDocId.current !== streamDocId) return;
        setChatLog((l) => [...l, { role: "assistant", text: m }]);
      },
      onStreamEnd: () => setBusy(false),
    });
  };

  const undo = async () => {
    if (!doc || busy) return;
    try {
      setDoc(await api.undoResume(doc.id, doc.rev));
      setChatWarnings([]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) await load();
      else setError(errorMessage(e));
    }
  };

  const promote = async (confirm: boolean) => {
    if (!analysisId || busy) return;
    setBusy(true);
    try {
      await api.saveToMaster(analysisId, null, confirm);
      setConfirmPromote(null);
      setNotice("Saved to your master resume.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const detail = e.detail as { warnings?: ValidationWarning[] } | undefined;
        setConfirmPromote(detail?.warnings ?? []);
      } else {
        setError(errorMessage(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const retailor = async () => {
    if (!doc || !analysisId || busy) return;
    setBusy(true);
    try {
      setDoc(await api.retailorAnalysis(analysisId, doc.rev));
      setChatWarnings([]);
      setNotice("Re-tailored from your current master resume. Undo is available.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) await load();
      else setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const downloadFile = async (kind: "pdf" | "docx") => {
    if (!analysisId) return;
    try {
      const blob =
        kind === "pdf"
          ? await api.downloadResumePdf(analysisId)
          : await api.downloadResumeDocx(analysisId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jobfit-resume-${analysisId}.${kind}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errorMessage(e, `Couldn't download the ${kind.toUpperCase()}`));
    }
  };

  if (error)
    return (
      <div className="rounded-2xl border border-rose-100 bg-rose-50 p-6 text-sm text-rose-600">
        {error}
      </div>
    );
  if (!doc)
    return (
      <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-10 text-center text-sm text-[#71717a]">
        Loading your resume…
      </div>
    );

  const allWarnings = [...doc.warnings, ...chatWarnings];

  return (
    <div className="space-y-5">
      {notice && (
        <div className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-2.5 text-sm text-amber-700">
          {notice}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
        {/* Left: controls + chat */}
        <div className="flex max-h-[calc(100vh-13rem)] flex-col gap-4 rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-[#71717a]">
              Edit inline, or tell the editor what to change. It follows your rules and flags
              anything not in your profile.
            </p>
            <StatusPill tone="neutral">rev {doc.rev}</StatusPill>
          </div>

          {!isFork ? (
            <div className="flex items-center gap-2">
              <select
                value={doc.id}
                disabled={busy}
                onChange={async (e) => {
                  if (busy) return;
                  cancelStream.current?.();
                  await api.patchResumeVersion(e.target.value, { make_active: true });
                  await load();
                }}
                className={INPUT}
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                    {v.is_active ? " (active)" : ""}
                  </option>
                ))}
              </select>
              <SecondaryButton
                type="button"
                disabled={busy}
                className="shrink-0 !px-3"
                onClick={async () => {
                  if (busy) return;
                  const name = window.prompt("Name this version", "New version");
                  if (name) {
                    cancelStream.current?.();
                    await api.createResumeVersion(name, true);
                    await load();
                  }
                }}
              >
                <Plus className="size-4" /> New
              </SecondaryButton>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <PrimaryButton type="button" onClick={() => void promote(false)} disabled={busy}>
                Save to master
              </PrimaryButton>
              <SecondaryButton type="button" onClick={() => void retailor()} disabled={busy}>
                <RefreshCw className="size-4" /> Re-tailor
              </SecondaryButton>
            </div>
          )}

          {allWarnings.length > 0 && <WarningChips warnings={allWarnings} />}

          {/* Chat thread */}
          <div
            ref={threadRef}
            className="flex-1 space-y-2.5 overflow-y-auto rounded-xl border border-[rgba(0,0,0,0.05)] bg-[#faf9f7] p-3"
          >
            {chatLog.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
                <Sparkles className="size-5 text-[#5b5bd6]" />
                <p className="text-sm text-[#71717a]">
                  Tell me what to change, or set a rule with{" "}
                  <span className="font-medium text-[#0f0f17]">“always”</span> /{" "}
                  <span className="font-medium text-[#0f0f17]">“never”</span> and I’ll follow it on
                  every future edit.
                </p>
              </div>
            ) : (
              chatLog.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.role === "user"
                      ? "ml-8 rounded-xl rounded-tr-sm bg-[#0f0f17] px-3 py-2 text-sm text-white"
                      : "mr-8 rounded-xl rounded-tl-sm border border-[rgba(91,91,214,0.15)] bg-[#ededf8] px-3 py-2 text-sm text-[#3d3d80]"
                  }
                >
                  {line.text}
                </div>
              ))
            )}
            {busy && (
              <div className="mr-8 inline-flex items-center gap-1.5 rounded-xl bg-[#ededf8] px-3 py-2 text-sm text-[#71717a]">
                <span className="size-1.5 animate-pulse rounded-full bg-[#5b5bd6]" /> Editing…
              </div>
            )}
          </div>

          {/* Input */}
          <div className="flex items-end gap-2">
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendChat();
                }
              }}
              rows={2}
              placeholder="Tell the editor what to change…"
              className={`${INPUT} resize-none`}
            />
            <button
              type="button"
              onClick={sendChat}
              disabled={busy || !instruction.trim()}
              aria-label="Send"
              className="shrink-0 rounded-xl bg-[#5b5bd6] p-2.5 text-white transition-colors hover:bg-[#4f4fc9] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="size-4" />
            </button>
          </div>

          {/* v1 undo affordance: single-step undo + rev indicator. Full revision
              browser (listResumeRevisions/restoreResume) deferred. */}
          <div className="flex items-center gap-4 border-t border-[rgba(0,0,0,0.05)] pt-3 text-xs text-[#71717a]">
            <button
              type="button"
              onClick={() => void undo()}
              disabled={busy}
              className="inline-flex items-center gap-1 transition-colors hover:text-[#0f0f17] disabled:opacity-50"
            >
              <Undo2 className="size-3.5" /> Undo
            </button>
            {isFork && (
              <div className="ml-auto flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void downloadFile("pdf")}
                  className="inline-flex items-center gap-1 transition-colors hover:text-[#0f0f17]"
                >
                  <Download className="size-3.5" /> PDF
                </button>
                <button
                  type="button"
                  onClick={() => void downloadFile("docx")}
                  className="inline-flex items-center gap-1 transition-colors hover:text-[#0f0f17]"
                >
                  <Download className="size-3.5" /> DOCX
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right: the resume, on paper */}
        <div className="overflow-y-auto rounded-2xl border border-[rgba(0,0,0,0.06)] bg-[#f0f0ee] p-4 sm:p-8">
          <ResumePreview content={doc.content} editable onFieldChange={applyInlineEdit} />
        </div>
      </div>

      {/* Promote-confirm dialog */}
      {confirmPromote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0f0f17]/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md space-y-4 rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-6 shadow-xl">
            <h3 className="text-base font-medium text-[#0f0f17]">Save to master?</h3>
            <p className="text-sm text-[#71717a]">
              Some content wasn’t found in your profile. Check it’s accurate before saving it to
              your master resume.
            </p>
            {confirmPromote.length > 0 && <WarningChips warnings={confirmPromote} />}
            <div className="flex justify-end gap-2 pt-1">
              <SecondaryButton type="button" onClick={() => setConfirmPromote(null)}>
                Cancel
              </SecondaryButton>
              <PrimaryButton type="button" onClick={() => void promote(true)} disabled={busy}>
                Save anyway
              </PrimaryButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
