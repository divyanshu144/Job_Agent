import type { ResourceItem } from "../types";
import { useState } from "react";

function Card({ item }: { item: ResourceItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-lg overflow-hidden">
      <button className="w-full flex justify-between p-4 bg-slate-50 text-left" onClick={() => setOpen(!open)}>
        <span className="font-medium">{item.skill}</span>
        <span className="text-xs text-slate-500">~{item.estimated_hours}h {open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="p-4 space-y-2 text-sm">
          {item.courses.length > 0 && <div><p className="font-semibold text-slate-600 mb-1">Courses</p><ul className="list-disc list-inside">{item.courses.map((c, i) => <li key={i}>{c}</li>)}</ul></div>}
          {item.books.length > 0 && <div><p className="font-semibold text-slate-600 mb-1">Books</p><ul className="list-disc list-inside">{item.books.map((b, i) => <li key={i}>{b}</li>)}</ul></div>}
          {item.projects.length > 0 && <div><p className="font-semibold text-slate-600 mb-1">Projects</p><ul className="list-disc list-inside">{item.projects.map((p, i) => <li key={i}>{p}</li>)}</ul></div>}
        </div>
      )}
    </div>
  );
}

export function ResourcePanel({ gaps }: { gaps: ResourceItem[] }) {
  if (!gaps.length) return <p className="text-slate-500 text-sm">No resources needed.</p>;
  return <div className="space-y-4">{gaps.map(g => <Card key={g.skill} item={g} />)}</div>;
}
