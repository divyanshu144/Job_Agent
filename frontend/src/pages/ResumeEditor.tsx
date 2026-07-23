import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download, History, RefreshCw, Send, Undo2 } from "lucide-react";
import { api, ApiError, errorMessage, streamResumeChat } from "../api/client";
import { ResumePreview } from "../components/ResumePreview";
import { WarningChips } from "../components/WarningChips";
import type {
  ResumeDocumentResponse,
  ResumeTailorerOutput,
  ResumeVersionSummary,
  ValidationWarning,
} from "../types";

type ChatLine = { role: "user" | "assistant"; text: string };

export function ResumeEditor() {
  const { analysisId } = useParams<{ analysisId?: string }>();
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

  const load = useCallback(async () => {
    try {
      const d = isFork
        ? await api.getAnalysisResume(analysisId!)
        : await api.getMasterResume();
      setDoc(d);
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

  const onConflict = useCallback(
    (rev: number, content: ResumeTailorerOutput) => {
      setDoc((d) => (d ? { ...d, rev, content } : d));
      setNotice("Resume changed elsewhere — reloaded the latest version.");
    },
    [],
  );

  const applyInlineEdit = async (mutate: (draft: ResumeTailorerOutput) => void) => {
    if (!doc) return;
    const draft: ResumeTailorerOutput = JSON.parse(JSON.stringify(doc.content));
    mutate(draft);
    try {
      const updated = await api.patchResumeContent(doc.id, doc.rev, draft);
      setDoc(updated);
      setNotice(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        await load();
        setNotice("Resume changed elsewhere — reloaded; your last edit was not applied.");
      } else {
        setError(errorMessage(e));
      }
    }
  };

  const sendChat = () => {
    if (!doc || !instruction.trim() || busy) return;
    const text = instruction.trim();
    // Captured so a late-arriving event from this stream can be dropped if the
    // user has since switched to a different document (see Fix 1 in review).
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
        const rule = r.new_rule ? ` · Rule saved: ${r.new_rule.mode} ${r.new_rule.text}` : "";
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
    if (!doc) return;
    try {
      setDoc(await api.undoResume(doc.id, doc.rev));
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
        // 409 detail shape from the backend: { message, warnings }
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
    if (!doc || !analysisId) return;
    setBusy(true);
    try {
      setDoc(await api.retailorAnalysis(analysisId, doc.rev));
      setNotice("Re-tailored from your current master (undo available).");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) await load();
      else setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  // Blob-anchor download (matches Results.tsx's house pattern) rather than
  // window.open — keeps download error handling in one place with the rest
  // of the page's error state instead of relying on a raw browser navigation.
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
      setError(errorMessage(e, `Failed to download ${kind.toUpperCase()}`));
    }
  };

  if (error) return <p className="p-8 text-sm text-red-400">{error}</p>;
  if (!doc) return <p className="p-8 text-sm text-neutral-400">Loading resume…</p>;

  const allWarnings = [...doc.warnings, ...chatWarnings];

  return (
    <div className="flex h-full gap-6 p-6">
      {/* Left: chat + controls */}
      <div className="flex w-96 shrink-0 flex-col gap-4">
        {!isFork && (
          <div className="flex items-center gap-2 text-sm">
            <select
              value={doc.id}
              disabled={busy}
              onChange={async (e) => {
                if (busy) return;
                cancelStream.current?.();
                await api.patchResumeVersion(e.target.value, { make_active: true });
                await load();
              }}
              className="flex-1 rounded border border-neutral-700 bg-[#0f0f17] px-2 py-1.5 disabled:opacity-50"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                  {v.is_active ? " (active)" : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={busy}
              className="rounded border border-neutral-700 px-2 py-1.5 text-neutral-300 hover:border-[#5b5bd6] disabled:opacity-50"
              onClick={async () => {
                if (busy) return;
                const name = window.prompt("Version name", "New version");
                if (name) {
                  cancelStream.current?.();
                  await api.createResumeVersion(name, true);
                  await load();
                }
              }}
            >
              + New
            </button>
          </div>
        )}

        {isFork && (
          <div className="flex flex-wrap gap-2 text-sm">
            <button
              type="button"
              onClick={() => void promote(false)}
              disabled={busy}
              className="rounded bg-[#5b5bd6] px-3 py-1.5 font-medium text-white hover:bg-[#6b6be0] disabled:opacity-50"
            >
              Save to master
            </button>
            <button
              type="button"
              onClick={() => void retailor()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded border border-neutral-700 px-3 py-1.5 text-neutral-300 hover:border-[#5b5bd6] disabled:opacity-50"
            >
              <RefreshCw className="size-3.5" /> Re-tailor
            </button>
            <Link
              to={`/results/${analysisId}`}
              className="rounded border border-neutral-700 px-3 py-1.5 text-neutral-300 hover:border-[#5b5bd6]"
            >
              ← Results
            </Link>
          </div>
        )}

        <WarningChips warnings={allWarnings} />
        {notice && <p className="text-xs text-amber-300">{notice}</p>}

        <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-neutral-800 p-3 text-sm">
          {chatLog.length === 0 && (
            <p className="text-neutral-500">
              Tell me what to change, or set a rule with "always" / "never" and I'll follow it on
              every future edit.
            </p>
          )}
          {chatLog.map((line, i) => (
            <p key={i} className={line.role === "user" ? "text-neutral-100" : "text-[#9b9bf0]"}>
              {line.text}
            </p>
          ))}
          {busy && <p className="animate-pulse text-neutral-500">Editing…</p>}
        </div>

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
            className="flex-1 resize-none rounded border border-neutral-700 bg-[#0f0f17] px-3 py-2 text-sm outline-none focus:border-[#5b5bd6]"
          />
          <button
            type="button"
            onClick={sendChat}
            disabled={busy || !instruction.trim()}
            aria-label="Send"
            className="rounded bg-[#5b5bd6] p-2 text-white disabled:opacity-40"
          >
            <Send className="size-4" />
          </button>
        </div>

        {/* v1 undo affordance: single-step undo + rev indicator. Full revision
            browser (listResumeRevisions/restoreResume) deferred. */}
        <div className="flex items-center gap-3 text-xs text-neutral-400">
          <button
            type="button"
            onClick={() => void undo()}
            disabled={busy}
            className="inline-flex items-center gap-1 hover:text-neutral-200 disabled:opacity-50"
          >
            <Undo2 className="size-3.5" /> Undo
          </button>
          <span className="inline-flex items-center gap-1">
            <History className="size-3.5" /> rev {doc.rev}
          </span>
          {isFork && (
            <>
              <button
                type="button"
                className="inline-flex items-center gap-1 hover:text-neutral-200"
                onClick={() => void downloadFile("pdf")}
              >
                <Download className="size-3.5" /> PDF
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1 hover:text-neutral-200"
                onClick={() => void downloadFile("docx")}
              >
                <Download className="size-3.5" /> DOCX
              </button>
            </>
          )}
        </div>
      </div>

      {/* Right: live preview */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <ResumePreview content={doc.content} editable onFieldChange={applyInlineEdit} />
      </div>

      {/* Promote-confirm dialog */}
      {confirmPromote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md space-y-4 rounded-lg border border-neutral-700 bg-[#16161f] p-6">
            <h3 className="font-semibold">Unverified claims</h3>
            <p className="text-sm text-neutral-300">
              Some content wasn't found in your profile. Verify it's accurate before saving to
              your master resume.
            </p>
            <WarningChips warnings={confirmPromote} />
            <div className="flex justify-end gap-2 text-sm">
              <button
                type="button"
                onClick={() => setConfirmPromote(null)}
                className="rounded border border-neutral-700 px-3 py-1.5 text-neutral-300"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void promote(true)}
                disabled={busy}
                className="rounded bg-[#5b5bd6] px-3 py-1.5 font-medium text-white disabled:opacity-50"
              >
                Save anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
