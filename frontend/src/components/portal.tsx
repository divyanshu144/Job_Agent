import type { ComponentType, ReactNode } from "react";

type IconType = ComponentType<{ className?: string }>;

export function PageShell({ children, width = "wide" }: { children: ReactNode; width?: "wide" | "medium" }) {
  return (
    <div className={`mx-auto space-y-6 ${width === "wide" ? "max-w-7xl" : "max-w-5xl"}`}>
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
    <section className="rounded-3xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8">
      <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
        <div>
          {eyebrow && (
            <p className="mb-3 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              {eyebrow}
            </p>
          )}
          <h2 className="text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
            {title}
          </h2>
          {description && (
            <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">{description}</p>
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
    <section className={`rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6 ${className}`}>
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
        <h3 className="text-base font-semibold text-zinc-950">{title}</h3>
        {description && <p className="mt-1 text-sm text-zinc-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}

const statusStyles = {
  neutral: "border-zinc-200 bg-zinc-50 text-zinc-700",
  info: "border-blue-200 bg-blue-50 text-blue-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  danger: "border-rose-200 bg-rose-50 text-rose-700",
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
    <span className={`inline-flex items-center rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusStyles[tone]}`}>
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
    <div className="rounded-3xl border border-dashed border-zinc-200 bg-white p-10 text-center">
      {Icon && <Icon className="mx-auto size-9 text-zinc-400" />}
      <p className="mt-4 text-sm font-semibold text-zinc-800">{title}</p>
      {description && <p className="mt-1 text-sm text-zinc-500">{description}</p>}
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
      className={`inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
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
      className={`inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
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
      className={`inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 ${className}`}
      {...props}
    >
      {children}
    </a>
  );
}
