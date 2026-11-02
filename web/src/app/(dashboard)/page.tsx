"use client";

import Link from "next/link";
import { useState } from "react";
import { PhoneCall, PhoneForwarded, Quote } from "lucide-react";
import { api, useApi } from "@/lib/api";
import { fmtDateTime, humanize, timeAgo } from "@/lib/format";
import type { Alert, Plan, Report } from "@/lib/types";
import { useLive } from "@/components/Shell";
import { Button, Card, cx, Empty, ErrorNote, LEVEL_BAR, LevelBadge, PageHeader, PatientLink, Pill, Stat } from "@/components/ui";

type Today = {
  counts: {
    calls_today: number;
    completed_today: number;
    no_answer_today: number;
    open_alerts: number;
    open_urgent: number;
    flagged_patients_week: number;
    pending_followups: number;
  };
  alerts: Alert[];
  plans: Plan[];
  recent_reports: Report[];
};

const PLAN_TONE: Record<string, string> = {
  ringing: "bg-accent-soft text-accent",
  in_progress: "bg-accent-soft text-accent",
  retry: "bg-review-soft text-review",
  fallback: "bg-urgent-soft text-urgent",
};

export default function TodayPage() {
  const { data, error, reload } = useApi<Today>("/api/today");
  useLive((e) => {
    if (["alert", "alert_ack", "alert_assign", "report", "call", "ring", "fallback", "booking"].includes(e.type)) reload();
  });

  const c = data?.counts;
  return (
    <>
      <PageHeader
        title="Today"
        subtitle={new Date().toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "long", day: "numeric", month: "long" })}
      />
      <ErrorNote error={error} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Calls today" value={c?.calls_today ?? "–"} />
        <Stat label="Completed" value={c?.completed_today ?? "–"} />
        <Stat label="No answer" value={c?.no_answer_today ?? "–"} />
        <Stat label="Open alerts" value={c?.open_alerts ?? "–"} hint={c ? `${c.open_urgent} urgent or emergency` : undefined} tone={c?.open_urgent ? "URGENT" : undefined} />
        <Stat label="Flagged this week" value={c?.flagged_patients_week ?? "–"} hint="patients" />
        <Stat label="Pending follow-ups" value={c?.pending_followups ?? "–"} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Alert queue" action={<Link href="/flagged" className="text-xs text-accent hover:underline">All flagged patients →</Link>}>
            {data && data.alerts.length === 0 && <Empty>No open alerts. Nice.</Empty>}
            <ul className="divide-y divide-border">
              {data?.alerts.map((a) => <AlertRow key={a.id} alert={a} onChange={reload} />)}
            </ul>
          </Card>

          <Card title="Latest reports">
            {data && data.recent_reports.length === 0 && <Empty>No reports yet.</Empty>}
            <ul className="divide-y divide-border">
              {data?.recent_reports.map((r) => (
                <li key={r.id}>
                  <Link href={`/reports/${r.id}`} className="flex gap-3 px-4 py-3 hover:bg-surface-2">
                    <span className={cx("mt-1 h-2 w-2 shrink-0 rounded-full", LEVEL_BAR[r.urgency])} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-medium">{r.patient_name}</span>
                        <span className="text-faint">{r.pack_name}</span>
                        {r.status === "partial" && <Pill>partial</Pill>}
                        <span className="ml-auto text-xs text-faint">{timeAgo(r.created_at)}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-1 text-sm text-muted">{r.summary}</p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <LevelBadge level={r.urgency} />
                      {r.recovery_score != null && <span className="text-xs tabular-nums text-faint">score {r.recovery_score}</span>}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <Card title="Follow-up queue" className="h-fit">
          {data && data.plans.length === 0 && <Empty>Nothing scheduled.</Empty>}
          <ul className="divide-y divide-border">
            {data?.plans.map((p) => <PlanRow key={p.id} plan={p} onChange={reload} />)}
          </ul>
        </Card>
      </div>
    </>
  );
}

function AlertRow({ alert: a, onChange }: { alert: Alert; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const act = async (path: string, body?: object) => {
    setBusy(true);
    try {
      await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      onChange();
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="animate-in flex gap-3 px-4 py-3">
      <span className={cx("w-1 shrink-0 rounded-full", LEVEL_BAR[a.level])} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <LevelBadge level={a.level} />
          <PatientLink id={a.patient_id} name={a.patient_name} />
          <span className="text-sm">{a.reason}</span>
        </div>
        {a.evidence && (
          <p className="mt-1.5 flex gap-1.5 text-sm text-muted">
            <Quote size={13} className="mt-0.5 shrink-0 text-faint" />
            <span className="line-clamp-2">{a.evidence}</span>
          </p>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-faint">
          <span>{timeAgo(a.created_at)}</span>
          <span>·</span>
          <span>via {a.source === "lexicon" ? "live red-flag scan" : a.source === "rule" ? `rule ${a.rule_id}` : humanize(a.source)}</span>
          {a.assigned_to && <Pill>assigned: {a.assigned_to}</Pill>}
        </div>
      </div>
      <div className="flex shrink-0 flex-col gap-1.5">
        <Button size="sm" variant="primary" disabled={busy} onClick={() => act(`/api/alerts/${a.id}/ack`)}>
          Acknowledge
        </Button>
        <select
          disabled={busy}
          value=""
          onChange={(e) => e.target.value && act(`/api/alerts/${a.id}/assign`, { to: e.target.value })}
          className="h-7 rounded-lg border border-border bg-surface px-1.5 text-xs text-muted"
        >
          <option value="">Assign…</option>
          <option>On-call nurse</option>
          <option>Treating doctor</option>
          <option>Pharmacy</option>
        </select>
      </div>
    </li>
  );
}

function PlanRow({ plan: p, onChange }: { plan: Plan; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const callNow = async () => {
    setBusy(true);
    try {
      const res = await api<{ token: string }>(`/api/plans/${p.id}/ring`, { method: "POST" });
      window.open(`/call/${res.token}`, "_blank", "noopener");
      onChange();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="px-4 py-3">
      <div className="flex items-center gap-2">
        <PatientLink id={p.patient_id} name={p.patient_name} />
        <span className={cx("ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium", PLAN_TONE[p.status] ?? "bg-surface-2 text-muted")}>
          {humanize(p.status)}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-xs text-faint">
        <span>{humanize(p.pack_id.replace("_week1", ""))}</span>
        <span>·</span>
        <span>{p.language}</span>
        <span>·</span>
        <span title={fmtDateTime(p.due_at)}>due {timeAgo(p.due_at)}</span>
        {p.attempts > 0 && <span>· attempt {p.attempts}</span>}
      </div>
      <div className="mt-2 flex gap-1.5">
        <Button size="sm" onClick={callNow} disabled={busy}>
          <PhoneCall size={13} /> Call now
        </Button>
        <a href={`/call/${p.token}`} target="_blank" rel="noopener" className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs text-muted hover:bg-surface-2">
          <PhoneForwarded size={13} /> Patient link
        </a>
      </div>
    </li>
  );
}
