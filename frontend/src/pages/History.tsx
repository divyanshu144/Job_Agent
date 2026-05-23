import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AnalysisSummary } from "../types";

export function History() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.listHistory().then(setItems).finally(() => setLoading(false)); }, []);

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;
  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">History</h1>
      {!items.length && <p className="text-slate-500 text-sm">No analyses yet.</p>}
      <div className="space-y-2">
        {items.map(item => (
          <Link key={item.id} to={`/results/${item.id}`} className="block p-4 rounded-lg border hover:bg-slate-50">
            <p className="text-sm text-slate-700">{item.jd_text.slice(0, 120)}…</p>
            <p className="text-xs text-slate-400 mt-1">{new Date(item.created_at).toLocaleString()}</p>
            {item.partial && <span className="text-xs text-amber-600">partial</span>}
          </Link>
        ))}
      </div>
    </div>
  );
}
