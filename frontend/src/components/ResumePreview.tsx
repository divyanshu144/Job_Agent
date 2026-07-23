import { useEffect, useRef, useState } from "react";
import type { ResumeTailorerOutput } from "../types";

type Mutator = (draft: ResumeTailorerOutput) => void;

function EditableText({
  value,
  placeholder,
  multiline = false,
  editable,
  className = "",
  onCommit,
}: {
  value: string;
  placeholder: string;
  multiline?: boolean;
  editable: boolean;
  className?: string;
  onCommit: (next: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);
  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };
  if (!editable || !editing) {
    return (
      <span
        className={`${className} ${editable ? "cursor-text rounded px-0.5 hover:bg-[#5b5bd6]/10" : ""} ${value ? "" : "text-neutral-500 italic"}`}
        onClick={() => editable && setEditing(true)}
      >
        {value || placeholder}
      </span>
    );
  }
  const fieldClassName = `${className} w-full rounded border border-[#5b5bd6]/50 bg-[#0f0f17] px-1 outline-none`;
  return multiline ? (
    <textarea
      value={draft}
      onBlur={commit}
      className={fieldClassName}
      ref={(el) => {
        ref.current = el;
      }}
      rows={Math.max(2, Math.ceil(draft.length / 80))}
      onChange={(e) => setDraft(e.target.value)}
    />
  ) : (
    <input
      value={draft}
      onBlur={commit}
      className={fieldClassName}
      ref={(el) => {
        ref.current = el;
      }}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && commit()}
    />
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="border-b border-neutral-700 pb-1 text-xs font-bold uppercase tracking-widest text-neutral-300">
        {title}
      </h3>
      {children}
    </section>
  );
}

export function ResumePreview({
  content,
  editable = false,
  onFieldChange,
}: {
  content: ResumeTailorerOutput;
  editable?: boolean;
  onFieldChange?: (mutate: Mutator) => void;
}) {
  const change = (mutate: Mutator) => onFieldChange?.(mutate);
  return (
    <article className="mx-auto max-w-[52rem] space-y-6 rounded-lg bg-white/[0.03] p-8 font-serif text-sm leading-relaxed text-neutral-100">
      <header className="space-y-1 text-center">
        <EditableText
          value={content.headline}
          placeholder="Headline"
          editable={editable}
          className="text-xl font-bold"
          onCommit={(v) => change((d) => void (d.headline = v))}
        />
        <div>
          <EditableText
            value={content.summary}
            placeholder="Professional summary"
            multiline
            editable={editable}
            className="block text-left text-sm text-neutral-300"
            onCommit={(v) => change((d) => void (d.summary = v))}
          />
        </div>
      </header>

      {(content.skills.length > 0 || editable) && (
        <Section title="Skills">
          <p>{content.skills.join(" · ")}</p>
        </Section>
      )}

      {(content.experience.length > 0 || editable) && (
        <Section title="Work Experience">
          {content.experience.map((exp, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-baseline justify-between gap-4">
                <span className="font-semibold">
                  {[exp.company, exp.role].filter(Boolean).join(" | ")}
                </span>
                <span className="shrink-0 text-xs text-neutral-400">{exp.dates}</span>
              </div>
              <ul className="list-disc space-y-0.5 pl-5">
                {exp.bullets.map((b, j) => (
                  <li key={j}>
                    <EditableText
                      value={b}
                      placeholder="Bullet"
                      multiline
                      editable={editable}
                      onCommit={(v) =>
                        change((d) => void (d.experience[i].bullets[j] = v))
                      }
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {(content.projects.length > 0 || editable) && (
        <Section title="Projects">
          {content.projects.map((proj, i) => (
            <div key={i} className="space-y-1">
              <span className="font-semibold">{proj.name}</span>
              {proj.description && <p className="text-neutral-300">{proj.description}</p>}
              <ul className="list-disc space-y-0.5 pl-5">
                {proj.bullets.map((b, j) => (
                  <li key={j}>
                    <EditableText
                      value={b}
                      placeholder="Bullet"
                      multiline
                      editable={editable}
                      onCommit={(v) => change((d) => void (d.projects[i].bullets[j] = v))}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {(content.education.length > 0 || editable) && (
        <Section title="Education">
          {content.education.map((edu, i) => (
            <div key={i} className="flex items-baseline justify-between gap-4">
              <span>
                <span className="font-semibold">{edu.institution}</span>
                {edu.degree ? `, ${edu.degree}` : ""}
              </span>
              <span className="shrink-0 text-xs text-neutral-400">{edu.dates}</span>
            </div>
          ))}
        </Section>
      )}
    </article>
  );
}
