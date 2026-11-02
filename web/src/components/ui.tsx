import Link from "next/link";
import type { ReactNode } from "react";
import type { Level } from "@/lib/types";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

const LEVEL_STYLE: Record<Level, string> = {
  EMERGENCY: "bg-emergency-soft text-emergency border-emergency/30",
  URGENT: "bg-urgent-soft text-urgent border-urgent/30",
  REVIEW: "bg-review-soft text-review border-review/30",
  ROUTINE: "bg-routine-soft text-routine border-routine/30",
};

export const LEVEL_BAR: Record<Level, string> = {
  EMERGENCY: "bg-emergency",
  URGENT: "bg-urgent",
  REVIEW: "bg-review",
  ROUTINE: "bg-routine",
};

export function LevelBadge({ level, className }: { level: Level; className?: string }) {
  return (
    <span className={cx("inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-semibold tracking-wide", LEVEL_STYLE[level], className)}>
      {level}
    </span>
  );
}

export function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted", className)}>
      {children}
    </span>
  );
}

export function Card({ children, className, title, action }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={cx("rounded-xl border border-border bg-surface", className)}>
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Level }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", tone === "EMERGENCY" && "text-emergency", tone === "URGENT" && "text-urgent")}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-faint">{hint}</div>}
    </div>
  );
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger"; size?: "sm" | "md" };

export function Button({ variant = "ghost", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
        variant === "primary" && "bg-accent text-white hover:opacity-90 dark:text-black",
        variant === "ghost" && "border border-border bg-surface hover:bg-surface-2",
        variant === "danger" && "bg-emergency text-white hover:opacity-90",
        className,
      )}
    />
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-10 text-center text-sm text-faint">{children}</div>;
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="mb-4 rounded-lg border border-emergency/30 bg-emergency-soft px-3 py-2 text-sm text-emergency">
      Couldn&apos;t reach the CareLoop API: {error}. Is the backend running on {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}?
    </div>
  );
}

export function PatientLink({ id, name }: { id: number; name: string | null }) {
  return (
    <Link href={`/patients/${id}`} className="font-medium hover:underline">
      {name ?? `Patient #${id}`}
    </Link>
  );
}

const RISK_STYLE = { low: "text-routine", medium: "text-review", high: "text-emergency" } as const;

export function RiskBadge({ band, score }: { band: "low" | "medium" | "high"; score: number }) {
  return (
    <span className={cx("text-xs font-medium", RISK_STYLE[band])} title="Heuristic readmission risk, not a validated model">
      {band} risk · {score}
    </span>
  );
}
