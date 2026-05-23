interface Props { score: number; matched: string[]; missing: string[]; partial: string[]; }

function Chips({ label, items, cls }: { label: string; items: string[]; cls: string }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-slate-500 uppercase mb-1">{label}</p>
      <div className="flex flex-wrap gap-1">
        {items.map(s => <span key={s} className={`px-2 py-0.5 rounded-full text-xs ${cls}`}>{s}</span>)}
      </div>
    </div>
  );
}

export function ScoreCard({ score, matched, missing, partial }: Props) {
  const c = score >= 70 ? "text-green-600" : score >= 50 ? "text-amber-500" : "text-red-500";
  return (
    <div className="p-6 rounded-xl border bg-white shadow-sm space-y-4">
      <div className="flex items-end gap-2">
        <span className={`text-6xl font-bold ${c}`}>{score}</span>
        <span className="text-slate-400 text-xl mb-1">/100</span>
      </div>
      <Chips label="Matched" items={matched} cls="bg-green-100 text-green-800" />
      <Chips label="Partial" items={partial} cls="bg-amber-100 text-amber-800" />
      <Chips label="Missing" items={missing} cls="bg-red-100 text-red-800" />
    </div>
  );
}
