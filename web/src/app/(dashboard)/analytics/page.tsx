"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "@/lib/api";
import { humanize } from "@/lib/format";
import { Card, ErrorNote, PageHeader, Stat } from "@/components/ui";

type Overview = {
  window_days: number;
  calls: { total: number; by_status: Record<string, number>; answer_rate: number | null; completion_rate: number | null };
  urgency: Record<string, number>;
  flagged_series: { date: string; REVIEW: number; URGENT: number; EMERGENCY: number }[];
  adherence_rate: number | null;
  languages: Record<string, number>;
  recovery_trend: Record<string, { week: string; avg_score: number; n: number }[]>;
  median_latency_ms: number | null;
};

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const tooltip = { contentStyle: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 } };
const SERIES = ["var(--accent)", "var(--urgent)", "var(--review)"];

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const { data, error } = useApi<Overview>(`/api/analytics?days=${days}`);

  const weeks = new Map<string, Record<string, number | string>>();
  for (const [pack, rows] of Object.entries(data?.recovery_trend ?? {})) {
    for (const r of rows) {
      const row = weeks.get(r.week) ?? { week: r.week };
      row[pack] = r.avg_score;
      weeks.set(r.week, row);
    }
  }
  const trend = [...weeks.values()].sort((a, b) => String(a.week).localeCompare(String(b.week)));
  const packs = Object.keys(data?.recovery_trend ?? {});

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Follow-up outcomes across the clinic"
        actions={
          <select className="h-9 rounded-lg border border-border bg-surface px-2 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
          </select>
        }
      />
      <ErrorNote error={error} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Calls placed" value={data?.calls.total ?? "–"} />
        <Stat label="Answer rate" value={pct(data?.calls.answer_rate ?? null)} />
        <Stat label="Completion rate" value={pct(data?.calls.completion_rate ?? null)} hint="of answered calls" />
        <Stat label="Medicine adherence" value={pct(data?.adherence_rate ?? null)} hint="doses fully taken" />
        <Stat label="Median response latency" value={data?.median_latency_ms ? `${Math.round(data.median_latency_ms)} ms` : "—"} hint="voice calls" />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title="Flags per day (last 14 days)">
          <div className="h-64 px-2 py-3">
            <ResponsiveContainer>
              <BarChart data={data?.flagged_series ?? []}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} stroke="var(--faint)" />
                <YAxis allowDecimals={false} fontSize={11} stroke="var(--faint)" width={28} />
                <Tooltip {...tooltip} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="REVIEW" stackId="a" fill="var(--review)" />
                <Bar dataKey="URGENT" stackId="a" fill="var(--urgent)" />
                <Bar dataKey="EMERGENCY" stackId="a" fill="var(--emergency)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Average recovery score by week">
          <div className="h-64 px-2 py-3">
            <ResponsiveContainer>
              <LineChart data={trend}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="week" fontSize={11} stroke="var(--faint)" />
                <YAxis domain={[0, 100]} fontSize={11} stroke="var(--faint)" width={28} />
                <Tooltip {...tooltip} />
                <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v: string) => humanize(v)} />
                {packs.map((p, i) => (
                  <Line key={p} dataKey={p} stroke={SERIES[i % SERIES.length]} strokeWidth={2} dot connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Report urgency">
          <Breakdown values={data?.urgency ?? {}} order={["ROUTINE", "REVIEW", "URGENT", "EMERGENCY"]} />
        </Card>
        <Card title="Call outcomes">
          <Breakdown values={data?.calls.by_status ?? {}} />
        </Card>
        <Card title="Languages" className="lg:col-span-2">
          <Breakdown values={data?.languages ?? {}} />
        </Card>
      </div>
      <p className="mt-4 text-xs text-faint">Readmission risk shown elsewhere is a transparent heuristic over flags, adherence, age and score trend, not a validated clinical model.</p>
    </>
  );
}

function Breakdown({ values, order }: { values: Record<string, number>; order?: string[] }) {
  const keys = order ?? Object.keys(values).sort((a, b) => values[b] - values[a]);
  const total = Object.values(values).reduce((a, b) => a + b, 0) || 1;
  return (
    <ul className="space-y-2 px-4 py-4">
      {keys.map((k) => (
        <li key={k} className="grid grid-cols-[8rem_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="truncate text-muted">{humanize(k)}</span>
          <span className="h-2 overflow-hidden rounded-full bg-surface-2">
            <span className="block h-full rounded-full bg-accent" style={{ width: `${((values[k] ?? 0) / total) * 100}%` }} />
          </span>
          <span className="text-right tabular-nums">{values[k] ?? 0}</span>
        </li>
      ))}
    </ul>
  );
}
