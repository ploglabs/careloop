"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { BarChart3, CalendarDays, ClipboardPlus, Flag, LayoutDashboard, MessageSquare, PanelLeft, Users, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { setRole, useLiveEvents, useRole, type LiveEvent, type Role } from "@/lib/api";
import { cx, LevelBadge } from "@/components/ui";
import type { Level } from "@/lib/types";

const NAV_GROUPS = [
  { title: "Overview", items: [
    { href: "/", label: "Today", icon: LayoutDashboard },
    { href: "/flagged", label: "Flagged", icon: Flag },
  ] },
  { title: "Patients", items: [
    { href: "/patients", label: "Patients", icon: Users },
    { href: "/schedule", label: "Schedule", icon: CalendarDays },
    { href: "/messages", label: "Messages", icon: MessageSquare },
    { href: "/intake", label: "New discharge", icon: ClipboardPlus },
  ] },
  { title: "Insights", items: [
    { href: "/analytics", label: "Analytics", icon: BarChart3 },
  ] },
];
const NAV = NAV_GROUPS.flatMap((g) => g.items);
const isActive = (pathname: string, href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

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

// Sidebar collapsed state: kept in memory, remembered per browser when storage is available.
const SIDEBAR_KEY = "careloop.sidebar";
const sidebarListeners = new Set<() => void>();
let collapsedState: boolean | null = null;

function sidebarCollapsed() {
  if (collapsedState === null) {
    try {
      collapsedState = localStorage.getItem(SIDEBAR_KEY) === "collapsed";
    } catch {
      collapsedState = false;
    }
  }
  return collapsedState;
}

function onSidebarChange(l: () => void) {
  sidebarListeners.add(l);
  return () => {
    sidebarListeners.delete(l);
  };
}

function toggleSidebar() {
  collapsedState = !sidebarCollapsed();
  try {
    localStorage.setItem(SIDEBAR_KEY, collapsedState ? "collapsed" : "open");
  } catch {}
  sidebarListeners.forEach((l) => l());
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const listeners = useRef(new Set<Listener>());
  const [toasts, setToasts] = useState<Toast[]>([]);
  const role = useRole();
  const collapsed = useSyncExternalStore(onSidebarChange, sidebarCollapsed, () => false);

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
      }
    }
  });

  return (
    <LiveContext.Provider value={{ subscribe }}>
      <div className="h-dvh bg-surface-2 md:p-2">
        <div className="flex h-full overflow-hidden border-border bg-surface md:rounded-2xl md:border md:shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
          <aside
            className={cx(
              "hidden shrink-0 flex-col overflow-y-auto overflow-x-hidden border-r border-border bg-bg py-4 transition-[width] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] md:flex",
              collapsed ? "w-[60px] px-2.5" : "w-56 px-3",
            )}
          >
            <Link href="/" className="mb-6 flex h-8 items-center gap-2.5 px-1.5" title="CareLoop">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo-mark.png" alt="CareLoop" width={22} height={22} className="h-[22px] w-[22px] shrink-0" />
              {!collapsed && <span className="whitespace-nowrap text-[15px] font-semibold tracking-tight">CareLoop</span>}
            </Link>
            <nav className="flex flex-col gap-5">
              {NAV_GROUPS.map((g) => (
                <div key={g.title}>
                  {collapsed ? (
                    <div className="mx-2 mb-2 h-px bg-border first:hidden" />
                  ) : (
                    <p className="mb-1 whitespace-nowrap px-2.5 text-xs text-faint">{g.title}</p>
                  )}
                  <div className="flex flex-col gap-0.5">
                    {g.items.map(({ href, label, icon: Icon }) => (
                      <Link
                        key={href}
                        href={href}
                        title={collapsed ? label : undefined}
                        className={cx(
                          "flex h-8 items-center gap-2.5 whitespace-nowrap rounded-lg px-2.5 text-[13px] transition-colors duration-150",
                          isActive(pathname, href) ? "bg-black/[0.07] font-medium text-text" : "text-text/80 hover:bg-black/[0.04] hover:text-text",
                        )}
                      >
                        <Icon size={15} strokeWidth={1.75} className="shrink-0" />
                        {!collapsed && label}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
            {!collapsed && (
              <div className="mt-auto space-y-3 px-2 pt-6 text-xs text-muted">
                <label className="block">
                  <span className="mb-1 block text-faint">Signed in as (demo)</span>
                  <select
                    value={role}
                    onChange={(e) => {
                      setRole(e.target.value as Role);
                      location.reload();
                    }}
                    className="h-8 w-full rounded-lg border border-border bg-surface px-2 text-[13px] text-text shadow-[0_1px_1px_rgba(0,0,0,0.03)]"
                  >
                    <option value="nurse">Nurse</option>
                    <option value="doctor">Doctor</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
                <p className="leading-snug text-faint">Synthetic demo data only.</p>
              </div>
            )}
          </aside>

          <div className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-surface">
            <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-border bg-surface px-4 py-2 md:hidden">
              {NAV.map(({ href, label }) => (
                <Link key={href} href={href} className={cx("whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm", isActive(pathname, href) ? "bg-black/[0.06] font-medium text-text" : "text-muted")}>
                  {label}
                </Link>
              ))}
            </nav>
            <header className="sticky top-0 z-10 hidden h-14 shrink-0 items-center gap-2 border-b border-border bg-surface/95 px-4 text-[13px] backdrop-blur md:flex">
              <button
                onClick={toggleSidebar}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                className="press mr-1 grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-black/[0.04] hover:text-text"
              >
                <PanelLeft size={16} strokeWidth={1.75} />
              </button>
              <span className="text-muted">CareLoop</span>
              <span className="text-faint">/</span>
              <span className="font-medium">{NAV.find((n) => isActive(pathname, n.href))?.label ?? "Details"}</span>
              <span className="ml-auto flex items-center gap-2 pr-4 text-xs text-muted">
                <span className={cx("relative h-1.5 w-1.5 rounded-full", connected ? "live-ping bg-routine" : "bg-faint")} />
                {connected ? "Live" : "Reconnecting…"}
              </span>
            </header>
            <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-7 md:px-10">{children}</main>
          </div>
        </div>
      </div>

      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <AlertToast key={t.id} toast={t} onDismiss={() => setToasts((all) => all.filter((x) => x.id !== t.id))} />
          ))}
        </AnimatePresence>
      </div>
    </LiveContext.Provider>
  );
}

const TOAST_MS = 12000;

/** Urgent alert toast: slides in from the edge it leaves by, and its timer pauses while hovered. */
function AlertToast({ toast: t, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const reduce = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const remaining = useRef(TOAST_MS);

  useEffect(() => {
    if (paused) return;
    const started = Date.now();
    const timer = setTimeout(onDismiss, remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current -= Date.now() - started;
    };
  }, [paused, onDismiss]);

  return (
    <motion.div
      layout={!reduce}
      initial={{ opacity: 0, transform: reduce ? "none" : "translateX(24px)" }}
      animate={{ opacity: 1, transform: "translateX(0px)" }}
      exit={{ opacity: 0, transform: reduce ? "none" : "translateX(24px)", transition: { duration: 0.18, ease: [0.4, 0, 1, 1] } }}
      transition={{ duration: 0.32, ease: [0.23, 1, 0.32, 1], layout: { duration: 0.24, ease: [0.23, 1, 0.32, 1] } }}
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      className={cx(
        "group pointer-events-auto relative rounded-xl border bg-surface shadow-[0_8px_30px_-12px_rgba(0,0,0,0.18)]",
        t.level === "EMERGENCY" ? "border-emergency/40" : "border-urgent/40",
      )}
    >
      <Link href={`/patients/${t.patientId}`} onClick={onDismiss} className="block p-3 pr-9">
        <div className="flex items-center gap-2">
          <LevelBadge level={t.level} />
          <span className="truncate text-[13px] font-semibold">{t.title}</span>
        </div>
        {t.body && <p className="mt-1.5 line-clamp-2 text-[13px] text-muted">&ldquo;{t.body}&rdquo;</p>}
      </Link>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="press absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text"
      >
        <X size={14} />
      </button>
    </motion.div>
  );
}
