"use client";

import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import type { Meta, PatientBrief, Report, Risk } from "@/lib/types";
import { useLive } from "@/components/Shell";
import { Card, Empty, ErrorNote, LevelBadge, PageHeader, RiskBadge } from "@/components/ui";

type Flagged = {
  days: number;
  count: number;
  patients: { patient: PatientBrief; report: Report; doctor: string; specialty: string; procedure: string; reasons: string[]; risk: Risk }[];
};

export default function FlaggedPage() {
  const [days, setDays] = useState(7);
  const [level, setLevel] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [language, setLanguage] = useState("");
  const qs = new URLSearchParams({ days: String(days), ...(level && { level }), ...(specialty && { specialty }), ...(language && { language }) });
  const { data, error, reload } = useApi<Flagged>(`/api/flagged?${qs}`);
  const { data: meta } = useApi<Meta>("/api/meta");
  useLive((e) => (e.type === "report" || e.type === "alert") && reload());
  const specialties = [...new Set(meta?.doctors.map((d) => d.specialty))];
  const select = "h-9 rounded-lg border border-border bg-surface px-2 text-sm";

  return (
    <>
      <PageHeader
        title="Flagged patients"
        subtitle={data ? `${data.count} patient${data.count === 1 ? "" : "s"} flagged in the last ${days} days` : undefined}
        actions={
          <>
            <select className={select} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={1}>24 hours</option><option value={7}>7 days</option><option value={30}>30 days</option>
            </select>
            <select className={select} value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">Review and above</option><option value="URGENT">Urgent and above</option><option value="EMERGENCY">Emergency</option>
            </select>
            <select className={select} value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
              <option value="">All specialties</option>
              {specialties.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </select>
            <select className={select} value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="">All languages</option>
              {meta?.languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          </>
        }
      />
      <ErrorNote error={error} />
      <Card>
        {data?.count === 0 && <Empty>No flagged patients for these filters.</Empty>}
        <ul className="divide-y divide-border">
          {data?.patients.map(({ patient: p, report: r, doctor, procedure, reasons, risk }) => (
            <li key={p.id} className="flex flex-wrap items-start gap-3 px-4 py-3">
              <LevelBadge level={r.urgency} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Link href={`/patients/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                  <span className="text-faint">{humanize(procedure)} · {doctor} · {p.language_name}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {reasons.map((reason, i) => (
                    <span key={i} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-xs text-muted">{reason}</span>
                  ))}
                </div>
              </div>
              <div className="text-right">
                <RiskBadge band={risk.band} score={risk.score} />
                <Link href={`/reports/${r.id}`} className="block text-xs text-accent hover:underline">{fmtDateTime(r.created_at)} report →</Link>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
