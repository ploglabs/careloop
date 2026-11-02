"use client";

import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import type { PatientBrief, Plan, Report, Risk } from "@/lib/types";
import { useLive } from "@/components/Shell";
import { Card, ErrorNote, LevelBadge, PageHeader, Pill, RiskBadge } from "@/components/ui";

type Row = PatientBrief & { latest_report: Report | null; next_plan: Plan | null; risk: Risk };

export default function PatientsPage() {
  const { data, error, reload } = useApi<Row[]>("/api/patients");
  const [q, setQ] = useState("");
  useLive((e) => e.type === "report" && reload());
  const rows = (data ?? []).filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHeader
        title="Patients"
        subtitle={data ? `${data.length} patients under follow-up` : undefined}
        actions={<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name" className="h-9 rounded-lg border border-border bg-surface px-3 text-sm" />}
      />
      <ErrorNote error={error} />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Patient</th>
                <th className="px-4 py-2.5 font-medium">Language</th>
                <th className="px-4 py-2.5 font-medium">Last check-in</th>
                <th className="px-4 py-2.5 font-medium">Next follow-up</th>
                <th className="px-4 py-2.5 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((p) => (
                <tr key={p.id} className="hover:bg-surface-2">
                  <td className="px-4 py-2.5">
                    <Link href={`/patients/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                    <div className="text-xs text-faint">{p.age ?? "?"} {p.sex ?? ""} · {p.phone}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    {p.language_name} {p.codemix && <Pill>code-mix</Pill>}
                  </td>
                  <td className="px-4 py-2.5">
                    {p.latest_report ? (
                      <Link href={`/reports/${p.latest_report.id}`} className="flex items-center gap-2 hover:underline">
                        <LevelBadge level={p.latest_report.urgency} />
                        <span className="text-xs text-faint">{fmtDateTime(p.latest_report.created_at)}</span>
                      </Link>
                    ) : <span className="text-faint">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-xs">
                    {p.next_plan ? <>{humanize(p.next_plan.status)} · {fmtDateTime(p.next_plan.due_at)}</> : <span className="text-faint">—</span>}
                  </td>
                  <td className="px-4 py-2.5"><RiskBadge band={p.risk.band} score={p.risk.score} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
