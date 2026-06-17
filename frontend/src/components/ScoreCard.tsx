interface Props {
  score: number;
  matched: string[];
  missing: string[];
  partial: string[];
}

function Chips({ label, items, cls }: { label: string; items: string[]; cls: string }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">{label}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((s) => (
          <span key={s} className={`rounded-lg border px-2.5 py-1 text-xs font-medium ${cls}`}>
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ScoreCard({ score, matched, missing, partial }: Props) {
  const tone =
    score >= 80
      ? { text: "text-emerald-700", bar: "bg-emerald-600", label: "Strong match" }
      : score >= 60
        ? { text: "text-amber-600", bar: "bg-amber-500", label: "Promising fit" }
        : { text: "text-zinc-700", bar: "bg-zinc-500", label: "Needs review" };

  return (
    <div className="rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="grid gap-6 xl:grid-cols-[280px_1fr]">
        <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
          <p className="text-sm font-medium text-zinc-600">Match score</p>
          <div className="mt-3 flex items-end gap-2">
            <span className={`text-7xl font-semibold tracking-tight ${tone.text}`}>{score}</span>
            <span className="mb-3 text-xl text-zinc-500">/100</span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-200">
            <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${Math.max(0, Math.min(score, 100))}%` }} />
          </div>
          <p className="mt-3 text-sm text-zinc-600">{tone.label}</p>
        </div>
        <div className="space-y-5">
          <Chips label="Matched" items={matched} cls="border-emerald-200 bg-emerald-50 text-emerald-700" />
          <Chips label="Partial" items={partial} cls="border-amber-200 bg-amber-50 text-amber-700" />
          <Chips label="Missing" items={missing} cls="border-rose-200 bg-rose-50 text-rose-700" />
        </div>
      </div>
    </div>
  );
}
