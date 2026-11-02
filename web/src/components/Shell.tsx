"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Activity, BarChart3, CalendarDays, ClipboardPlus, Flag, LayoutDashboard, MessageSquare, Users } from "lucide-react";
import { setRole, useLiveEvents, useRole, type LiveEvent, type Role } from "@/lib/api";
import { cx, LevelBadge } from "@/components/ui";
import type { Level } from "@/lib/types";

const NAV = [
  { href: "/", label: "Today", icon: LayoutDashboard },
  { href: "/flagged", label: "Flagged", icon: Flag },
  { href: "/patients", label: "Patients", icon: Users },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/schedule", label: "Schedule", icon: CalendarDays },
  { href: "/messages", label: "Messages", icon: MessageSquare },
  { href: "/intake", label: "New discharge", icon: ClipboardPlus },
];

type Listener = (e: LiveEvent) => void;
const LiveContext = createContext<{ subscribe: (l: Listener) => () => void }>({ subscribe: () => () => {} });

/** Pages call this to refetch when relevant live events arrive. */
export function useLive(onEvent: Listener) {
  const { subscribe } = useContext(LiveContext);
  const ref = useRef(onEvent);
  useEffect(() => {
    ref.current = onEvent;
  });
  useEffect(() => subscribe((e) => ref.current(e)), [subscribe]);
}

type Toast = { id: number; level: Level; title: string; body: string; patientId: number };

function beep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
  } catch {}
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const listeners = useRef(new Set<Listener>());
  const [toasts, setToasts] = useState<Toast[]>([]);
  const role = useRole();

  const subscribe = useCallback((l: Listener) => {
    listeners.current.add(l);
    return () => {
      listeners.current.delete(l);
    };
  }, []);

  const connected = useLiveEvents((e) => {
    listeners.current.forEach((l) => l(e));
    if (e.type === "alert") {
      const d = e.data as { level: Level; reason: string; evidence: string; patient_name: string; patient_id: number; raised: boolean };
      if (d.level === "URGENT" || d.level === "EMERGENCY") {
        const id = Date.now() + Math.random();
        setToasts((t) => [{ id, level: d.level, title: `${d.patient_name}: ${d.reason}`, body: d.evidence, patientId: d.patient_id }, ...t].slice(0, 4));
        beep();
        setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 12000);
      }
    }
  });

  return (
    <LiveContext.Provider value={{ subscribe }}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-border bg-surface px-3 py-4 md:flex">
          <Link href="/" className="mb-6 flex items-center gap-2 px-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-white dark:text-black">
              <Activity size={16} />
            </span>
            <span className="font-semibold tracking-tight">CareLoop</span>
          </Link>
          <nav className="flex flex-col gap-0.5">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cx(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                    active ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface-2 hover:text-text",
                  )}
                >
                  <Icon size={16} />
                  {label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto space-y-3 px-2 text-xs text-muted">
            <div className="flex items-center gap-2">
              <span className={cx("h-2 w-2 rounded-full", connected ? "bg-routine" : "bg-faint")} />
              {connected ? "Live" : "Reconnecting…"}
            </div>
            <label className="block">
              <span className="mb-1 block text-faint">Signed in as (demo)</span>
              <select
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as Role);
                  location.reload();
                }}
                className="w-full rounded-md border border-border bg-surface px-2 py-1 text-text"
              >
                <option value="nurse">Nurse</option>
                <option value="doctor">Doctor</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <p className="leading-snug text-faint">Synthetic demo data only.</p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <nav className="flex gap-1 overflow-x-auto border-b border-border bg-surface px-4 py-2 md:hidden">
            {NAV.map(({ href, label }) => (
              <Link key={href} href={href} className={cx("whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm", pathname === href ? "bg-accent-soft text-accent" : "text-muted")}>
                {label}
              </Link>
            ))}
          </nav>
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </div>

      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <Link
            href={`/patients/${t.patientId}`}
            key={t.id}
            className={cx(
              "animate-in pointer-events-auto rounded-xl border bg-surface p-3 shadow-lg",
              t.level === "EMERGENCY" ? "border-emergency" : "border-urgent",
            )}
          >
            <div className="flex items-center gap-2">
              <LevelBadge level={t.level} />
              <span className="truncate text-sm font-semibold">{t.title}</span>
            </div>
            {t.body && <p className="mt-1.5 line-clamp-2 text-sm text-muted">&ldquo;{t.body}&rdquo;</p>}
          </Link>
        ))}
      </div>
    </LiveContext.Provider>
  );
}
