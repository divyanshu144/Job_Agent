import { useState } from "react";
import { Clipboard, Download } from "lucide-react";

export function DocViewer({ title, content, filename }: { title: string; content: string; filename: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  const download = () => {
    const b = new Blob([content], { type: "text/plain" });
    const u = URL.createObjectURL(b);
    const a = document.createElement("a");
    a.href = u; a.download = filename; a.click();
    URL.revokeObjectURL(u);
  };
  return (
    <div className="space-y-3 rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
        <h3 className="font-semibold text-zinc-950">{title}</h3>
        <div className="flex gap-2">
          <button
            onClick={copy}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-50 sm:flex-none"
          >
            <Clipboard className="size-3.5" />
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            onClick={download}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-50 sm:flex-none"
          >
            <Download className="size-3.5" />
            Download
          </button>
        </div>
      </div>
      <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-800">
        {content}
      </pre>
    </div>
  );
}
