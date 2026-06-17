import type { GapItem } from "../types";
import { useState } from "react";

function Row({ item, critical }: { item: GapItem; critical: boolean }) {
  const [open, setOpen] = useState(false);
  const cls = critical
    ? "border-rose-200 bg-rose-50"
    : "border-amber-200 bg-amber-50";
  const label = critical ? "High impact" : "Nice to have";

  return (
    <button
      type="button"
      className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition-colors hover:bg-white ${cls}`}
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="font-medium text-zinc-950">{item.skill}</span>
          <p className="mt-1 text-xs font-medium text-zinc-500">{label}</p>
        </div>
        <span className="text-xs text-zinc-500">{open ? "Collapse" : "Details"}</span>
      </div>
      {open && (
        <div className="mt-3 space-y-2 text-sm leading-6 text-zinc-700">
          <p><span className="font-semibold text-zinc-950">Impact:</span> {item.impact}</p>
          <p><span className="font-semibold text-zinc-950">Why:</span> {item.rationale}</p>
        </div>
      )}
    </button>
  );
}

export function GapList({ critical, niceToHave }: { critical: GapItem[]; niceToHave: GapItem[] }) {
  return (
    <div className="space-y-4">
      {critical.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-rose-700">High-impact gaps</h3>
          <div className="space-y-2">{critical.map((g) => <Row key={g.skill} item={g} critical />)}</div>
        </div>
      )}
      {niceToHave.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-amber-700">Nice-to-have gaps</h3>
          <div className="space-y-2">{niceToHave.map((g) => <Row key={g.skill} item={g} critical={false} />)}</div>
        </div>
      )}
      {!critical.length && !niceToHave.length && (
        <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600">
          No gaps identified for this package.
        </div>
      )}
    </div>
  );
}
