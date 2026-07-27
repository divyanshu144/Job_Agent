import { FileText } from "lucide-react";
import { ResumeEditorPanel } from "../components/ResumeEditorPanel";

export function ResumeEditor() {
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5">
        <p className="mb-1 flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">
          <FileText className="size-3.5" />
          Master resume
        </p>
        <h2 className="text-2xl font-medium tracking-[-0.03em] text-[#0f0f17]">Resume editor</h2>
        <p className="mt-1 text-sm text-[#71717a]">
          This is your reusable base resume. Tailored copies for each role are edited from the
          Results page.
        </p>
      </div>
      <ResumeEditorPanel />
    </div>
  );
}
