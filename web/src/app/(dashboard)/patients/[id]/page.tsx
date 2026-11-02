"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import type { Call, PatientBrief, Plan, Report, Risk } from "@/lib/types";
import { useLive } from "@/components/Shell";
import { Button, Card, cx, Empty, ErrorNote, LevelBadge, PageHeader, Pill, RiskBadge } from "@/components/ui";

type Detail = {
  patient: PatientBrief;
  risk: Risk;
  encounters: { id: number; procedure_type: string; doctor: string; specialty: string; discharged_at: string; medications: string[] }[];
  plans: Plan[];
  reports: Report[];
  calls: Call[];
  appointments: { id: number; doctor: string; start: string; status: string; source: string }[];
  adherence: { id: number; medication: string; taken: string; reason: string; recorded_at: string }[];
  consents: { id: number; granted: boolean; created_at: string; withdrawn_at: string | null; language: string }[];
};

export default function PatientPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, reload } = useApi<Detail>(`/api/patients/${id}`);
  useLive((e) => (e.data as { patient_id?: number }).patient_id === Number(id) && reload());
  if (!data) return <ErrorNote error={error} />;
  const { patient: p } = data;
  const trend = [...data.reports].reverse().filter((r) => r.recovery_score != null).map((r) => ({ date: fmtDate(r.created_at), score: r.recovery_score }));

  const withdraw = async () => {
    if (!confirm("Record consent withdrawal and stop all follow-up calls for this patient?")) return;
    await api(`/api/patients/${p.id}/consent/withdraw`, { method: "POST" });
    reload();
  };

  return (
    <>
      <PageHeader
        title={p.name}
        subtitle={<span>{p.age ?? "?"} {p.sex ?? ""} · {p.language_name}{p.codemix ? " (code-mixed)" : ""} · {p.phone}</span>}
        actions={<><RiskBadge band={data.risk.band} score={data.risk.score} /><Button size="sm" onClick={withdraw}>Withdraw consent</Button></>}
      />
      {data.risk.factors.length > 0 && (
        <p className="-mt-3 mb-5 text-xs text-faint">Heuristic risk factors: {data.risk.factors.join(", ")}</p>
      )}
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Check-in reports">
            {data.reports.length === 0 && <Empty>No check-ins yet.</Empty>}
            <ul className="divide-y divide-border">
              {data.reports.map((r) => (
                <li key={r.id}>
                  <Link href={`/reports/${r.id}`} className="flex items-start gap-3 px-4 py-3 hover:bg-surface-2">
                    <LevelBadge level={r.urgency} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{r.pack_name} <span className="font-normal text-faint">· {fmtDateTime(r.created_at)}</span></div>
                      <p className="line-clamp-2 text-sm text-muted">{r.summary}</p>
                    </div>
                    {r.recovery_score != null && <span className="text-sm tabular-nums text-muted">{r.recovery_score}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          {trend.length > 1 && (
            <Card title="Recovery score">
              <div className="h-48 px-2 py-3">
                <ResponsiveContainer>
                  <LineChart data={trend}>
                    <XAxis dataKey="date" fontSize={11} stroke="var(--faint)" />
                    <YAxis domain={[0, 100]} fontSize={11} stroke="var(--faint)" width={30} />
                    <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
                    <Line dataKey="score" stroke="var(--accent)" strokeWidth={2} dot />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}
          <Card title="Calls">
            <ul className="divide-y divide-border text-sm">
              {data.calls.map((c) => (
                <li key={c.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="w-32 text-xs text-faint">{fmtDateTime(c.rang_at)}</span>
                  <Pill>{c.mode}</Pill>
                  <span className={cx(c.status === "no_answer" && "text-review")}>{humanize(c.status)}</span>
                  <span className="ml-auto text-xs text-faint">{c.language}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="space-y-5">
          <Card title="Discharges">
            <ul className="divide-y divide-border text-sm">
              {data.encounters.map((e) => (
                <li key={e.id} className="px-4 py-3">
                  <div className="font-medium">{humanize(e.procedure_type)}</div>
                  <div className="text-xs text-faint">{e.doctor} · {fmtDate(e.discharged_at)}</div>
                  <div className="mt-1 text-xs text-muted">{e.medications.join(", ")}</div>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Follow-up plan">
            <ul className="divide-y divide-border text-sm">
              {data.plans.map((pl) => (
                <li key={pl.id} className="flex items-center justify-between px-4 py-2.5">
                  <span>{fmtDate(pl.due_at)}</span>
                  <span className="text-xs text-muted">{humanize(pl.status)}{pl.attempts ? ` · ${pl.attempts} attempt(s)` : ""}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Appointments">
            {data.appointments.length === 0 && <Empty>None</Empty>}
            <ul className="divide-y divide-border text-sm">
              {data.appointments.map((a) => (
                <li key={a.id} className="px-4 py-2.5">
                  <div className={cx(a.status !== "booked" && "text-faint line-through")}>{fmtDateTime(a.start)}</div>
                  <div className="text-xs text-faint">{a.doctor} · {humanize(a.status)} · via {humanize(a.source)}</div>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Medicine adherence">
            {data.adherence.length === 0 && <Empty>No data</Empty>}
            <ul className="divide-y divide-border text-sm">
              {data.adherence.slice(0, 8).map((m) => (
                <li key={m.id} className="flex justify-between gap-2 px-4 py-2">
                  <span className="truncate">{m.medication}</span>
                  <span className={cx("shrink-0 text-xs", m.taken === "all" ? "text-routine" : "text-urgent")}>{m.taken} · {fmtDate(m.recorded_at)}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Consent log">
            <ul className="divide-y divide-border text-xs">
              {data.consents.map((c) => (
                <li key={c.id} className="flex justify-between px-4 py-2">
                  <span>{c.granted ? "Granted" : "Declined"} ({c.language})</span>
                  <span className="text-faint">{fmtDateTime(c.created_at)}{c.withdrawn_at ? " · withdrawn" : ""}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
