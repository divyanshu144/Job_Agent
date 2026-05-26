import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CostSummary, RunCost } from "../types";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function fmt(n: number, decimals = 4) {
  return n.toFixed(decimals);
}

export function Costs() {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [runs, setRuns] = useState<RunCost[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getCostSummary(), api.getCostRuns()])
      .then(([s, r]) => { setSummary(s); setRuns(r); })
      .catch((e) => setError((e as Error).message));
  }, []);

  const agentTotals = runs.flatMap((r) => r.agents).reduce<Record<string, { calls: number; cost_usd: number; total_latency: number }>>((acc, a) => {
    const prev = acc[a.agent_name] ?? { calls: 0, cost_usd: 0, total_latency: 0 };
    acc[a.agent_name] = {
      calls: prev.calls + a.calls,
      cost_usd: prev.cost_usd + a.cost_usd,
      total_latency: prev.total_latency + a.avg_latency_ms * a.calls,
    };
    return acc;
  }, {});

  const totalCost = summary?.total_cost_usd ?? 0;

  return (
    <div className="max-w-4xl mx-auto px-6 space-y-8">
      <h1 className="text-xl font-bold text-slate-900">LLM Cost Dashboard</h1>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Spent" value={`$${fmt(summary.total_cost_usd)}`} />
          <StatCard label="LLM Calls" value={summary.total_calls.toLocaleString()} />
          <StatCard label="Cache Hit Rate" value={`${(summary.cache_hit_rate * 100).toFixed(1)}%`} />
          <StatCard label="Real Calls" value={summary.real_calls.toLocaleString()} />
        </div>
      )}

      {runs.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-700">Runs</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <th className="px-5 py-2">Date</th>
                <th className="px-5 py-2">Type</th>
                <th className="px-5 py-2">Calls</th>
                <th className="px-5 py-2">Cost</th>
                <th className="px-5 py-2">P50 Latency</th>
                <th className="px-5 py-2">Cache Hits</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <React.Fragment key={r.id}>
                  <tr
                    onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                    className="border-b border-slate-50 hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-5 py-2 text-slate-600">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="px-5 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${r.type === "discovery" ? "bg-blue-50 text-blue-600 border-blue-100" : "bg-emerald-50 text-emerald-600 border-emerald-100"}`}>
                        {r.type}
                      </span>
                    </td>
                    <td className="px-5 py-2 text-slate-700">{r.total_calls}</td>
                    <td className="px-5 py-2 font-mono text-slate-700">${fmt(r.total_cost_usd)}</td>
                    <td className="px-5 py-2 text-slate-700">{r.latency_p50_ms}ms</td>
                    <td className="px-5 py-2 text-slate-700">{r.cached_calls}</td>
                  </tr>
                  {expandedId === r.id && r.agents.length > 0 && (
                    <tr className="bg-slate-50 border-b border-slate-100">
                      <td colSpan={6} className="px-8 py-3">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left text-slate-500">
                              <th className="pb-1">Agent</th>
                              <th className="pb-1">Calls</th>
                              <th className="pb-1">Cost</th>
                              <th className="pb-1">Avg Latency</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.agents.map((a) => (
                              <tr key={a.agent_name}>
                                <td className="py-0.5 font-mono text-slate-700">{a.agent_name}</td>
                                <td className="py-0.5 text-slate-600">{a.calls}</td>
                                <td className="py-0.5 font-mono text-slate-700">${fmt(a.cost_usd)}</td>
                                <td className="py-0.5 text-slate-600">{a.avg_latency_ms}ms</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(agentTotals).length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-700">Agent Totals (all runs)</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <th className="px-5 py-2">Agent</th>
                <th className="px-5 py-2">Total Calls</th>
                <th className="px-5 py-2">Total Cost</th>
                <th className="px-5 py-2">Avg Latency</th>
                <th className="px-5 py-2">% of Spend</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(agentTotals)
                .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
                .map(([name, data]) => (
                  <tr key={name} className="border-b border-slate-50">
                    <td className="px-5 py-2 font-mono text-slate-700">{name}</td>
                    <td className="px-5 py-2 text-slate-600">{data.calls}</td>
                    <td className="px-5 py-2 font-mono text-slate-700">${fmt(data.cost_usd)}</td>
                    <td className="px-5 py-2 text-slate-600">
                      {data.calls > 0 ? Math.round(data.total_latency / data.calls) : 0}ms
                    </td>
                    <td className="px-5 py-2 text-slate-600">
                      {totalCost > 0 ? ((data.cost_usd / totalCost) * 100).toFixed(1) : "0"}%
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {!summary && !error && (
        <p className="text-sm text-slate-400">Loading…</p>
      )}
    </div>
  );
}
