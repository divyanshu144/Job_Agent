import type { GapItem } from "../types";
import { useState } from "react";

function Row({ item, critical }: { item: GapItem; critical: boolean }) {
  const [open, setOpen] = useState(false);
  const cls = critical ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50";
  return (
    <div className={`border rounded-lg p-3 cursor-pointer ${cls}`} onClick={() => setOpen(!open)}>
      <div className="flex justify-between">
        <span className="font-medium">{item.skill}</span>
        <span className="text-xs text-slate-400">{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div className="mt-2 text-sm text-slate-600 space-y-1">
          <p><b>Impact:</b> {item.impact}</p>
          <p><b>Why:</b> {item.rationale}</p>
        </div>
      )}
    </div>
  );
}

export function GapList({ critical, niceToHave }: { critical: GapItem[]; niceToHave: GapItem[] }) {
  return (
    <div className="space-y-4">
      {critical.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-red-600 uppercase mb-2">Critical</h3>
          <div className="space-y-2">{critical.map(g => <Row key={g.skill} item={g} critical />)}</div>
        </div>
      )}
      {niceToHave.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-amber-600 uppercase mb-2">Nice to Have</h3>
          <div className="space-y-2">{niceToHave.map(g => <Row key={g.skill} item={g} critical={false} />)}</div>
        </div>
      )}
      {!critical.length && !niceToHave.length && <p className="text-slate-500 text-sm">No gaps identified.</p>}
    </div>
  );
}
