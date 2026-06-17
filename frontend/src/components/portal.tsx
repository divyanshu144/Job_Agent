import type { ComponentType, ReactNode } from "react";

type IconType = ComponentType<{ className?: string }>;

export function PageShell({ children, width = "wide" }: { children: ReactNode; width?: "wide" | "medium" }) {
  return (
    <div className={`mx-auto space-y-6 ${width === "wide" ? "max-w-5xl" : "max-w-3xl"}`}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5 sm:p-6">
      <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
        <div>
          {eyebrow && (
            <p className="mb-1 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">
              {eyebrow}
            </p>
          )}
          <h2 className="text-2xl font-medium tracking-[-0.03em] text-[#0f0f17]">
            {title}
          </h2>
          {description && (
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[#71717a]">{description}</p>
          )}
        </div>
        {actions && <div className="flex flex-col gap-3 sm:flex-row">{actions}</div>}
      </div>
    </section>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5 ${className}`}>
      {children}
    </section>
  );
}

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-3">
      <div>
        <h3 className="text-sm font-medium text-[#0f0f17]">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-[#71717a]">{description}</p>}
      </div>
      {action}
    </div>
  );
}

const statusStyles = {
  neutral: "border-[rgba(0,0,0,0.08)] bg-[#f0f0f4] text-[#71717a]",
  info: "border-[rgba(91,91,214,0.15)] bg-[#ededf8] text-[#5b5bd6]",
  success: "border-emerald-100 bg-emerald-50 text-emerald-700",
  warning: "border-amber-100 bg-amber-50 text-amber-700",
  danger: "border-rose-100 bg-rose-50 text-rose-600",
};

export type StatusTone = keyof typeof statusStyles;

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: StatusTone;
}) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${statusStyles[tone]}`}>
      {children}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon: Icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: IconType;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-[rgba(91,91,214,0.18)] bg-white p-10 text-center">
      {Icon && <Icon className="mx-auto size-8 text-[#d4d4d8]" />}
      <p className="mt-4 text-sm font-medium text-[#0f0f17]">{title}</p>
      {description && <p className="mt-1 text-sm text-[#71717a]">{description}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function PrimaryButton({
  children,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28] disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-xl border border-[rgba(0,0,0,0.08)] bg-white px-4 py-2.5 text-sm font-medium text-[#71717a] transition-colors hover:border-[rgba(0,0,0,0.15)] hover:text-[#0f0f17] disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function PrimaryLink({
  children,
  className = "",
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: ReactNode }) {
  return (
    <a
      className={`inline-flex items-center justify-center gap-2 rounded-xl bg-[#0f0f17] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1a1a28] ${className}`}
      {...props}
    >
      {children}
    </a>
  );
}
