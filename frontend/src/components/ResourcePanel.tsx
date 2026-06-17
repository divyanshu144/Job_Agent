import type { ResourceItem } from "../types";
import { useState } from "react";

function Card({ item }: { item: ResourceItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <button
        className="flex w-full justify-between gap-3 p-4 text-left transition-colors hover:bg-zinc-50"
        onClick={() => setOpen(!open)}
      >
        <span className="font-medium text-zinc-950">{item.skill}</span>
        <span className="shrink-0 text-xs font-medium text-blue-700">~{item.estimated_hours}h {open ? "Collapse" : "Details"}</span>
      </button>
      {open && (
        <div className="space-y-4 border-t border-zinc-200 p-4 text-sm text-zinc-700">
          {item.courses.length > 0 && <Section title="Courses" items={item.courses} />}
          {item.books.length > 0 && <Section title="Books" items={item.books} />}
          {item.projects.length > 0 && <Section title="Projects" items={item.projects} />}
        </div>
      )}
    </div>
  );
}

export function ResourcePanel({ gaps }: { gaps: ResourceItem[] }) {
  if (!gaps.length) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600">
        No recommendations needed for this package.
      </div>
    );
  }
  return <div className="space-y-3">{gaps.map((g) => <Card key={g.skill} item={g} />)}</div>;
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">{title}</p>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={index} className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
