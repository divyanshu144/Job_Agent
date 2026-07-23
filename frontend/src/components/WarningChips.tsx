import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import type { ValidationWarning } from "../types";

const RULE_COPY: Record<string, string> = {
  unsupported_employer: "Employer not found in your profile",
  unsupported_institution: "Institution not found in your profile",
  unsupported_skill: "Skill not found in your profile",
  unsupported_metric: "Number not found in your profile",
  style_dash: "Contains an em/en dash, rephrase or use commas",
};

export function WarningChips({ warnings }: { warnings: ValidationWarning[] }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const seen = new Set<string>();
  const unique = warnings.filter((w) => {
    const key = `${w.rule}|${w.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return !dismissed.has(key);
  });
  if (unique.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {unique.map((w) => {
        const key = `${w.rule}|${w.detail}`;
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300"
            title={w.rule === "style_dash" ? RULE_COPY.style_dash : w.detail}
          >
            <AlertTriangle className="size-3" />
            {RULE_COPY[w.rule] ?? w.detail}
            <button
              type="button"
              aria-label="Dismiss warning"
              onClick={() => setDismissed(new Set(dismissed).add(key))}
              className="ml-0.5 text-amber-300/60 hover:text-amber-200"
            >
              <X className="size-3" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
