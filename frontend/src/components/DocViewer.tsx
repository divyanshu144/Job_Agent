import { useState } from "react";

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
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h3 className="font-semibold text-slate-800">{title}</h3>
        <div className="flex gap-2">
          <button onClick={copy} className="px-3 py-1 text-xs rounded-md bg-slate-100 hover:bg-slate-200">{copied ? "Copied!" : "Copy"}</button>
          <button onClick={download} className="px-3 py-1 text-xs rounded-md bg-slate-100 hover:bg-slate-200">Download</button>
        </div>
      </div>
      <pre className="whitespace-pre-wrap text-sm bg-slate-50 rounded-lg p-4 border overflow-auto max-h-96">{content}</pre>
    </div>
  );
}
