"use client";

import { useState, type CSSProperties } from "react";
import { BarChart } from "@/components/dither-kit/bar-chart";
import { Bar } from "@/components/dither-kit/bar";
import { LineChart } from "@/components/dither-kit/area-chart";
import { Line } from "@/components/dither-kit/area";
import { PieChart } from "@/components/dither-kit/pie-chart";
import { Pie } from "@/components/dither-kit/pie";
import { BlockLegend } from "@/components/dither-kit/block-legend";
import { Grid } from "@/components/dither-kit/grid";
import { Tooltip } from "@/components/dither-kit/tooltip";
import { XAxis } from "@/components/dither-kit/x-axis";
import { YAxis } from "@/components/dither-kit/y-axis";
import type { ChartConfig } from "@/components/dither-kit/chart-context";
import type { DitherColor } from "@/components/dither-kit/palette";
import { useApi } from "@/lib/api";
import { humanize } from "@/lib/format";
import { Card, Empty, ErrorNote, PageHeader, Stat } from "@/components/ui";

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

const LEVELS = ["ROUTINE", "REVIEW", "URGENT", "EMERGENCY"] as const;
const LEVEL_COLOR: Record<(typeof LEVELS)[number], DitherColor> = { ROUTINE: "green", REVIEW: "amber", URGENT: "orange", EMERGENCY: "red" };
const levelConfig = (levels: readonly (typeof LEVELS)[number][]): ChartConfig =>
  Object.fromEntries(levels.map((l) => [l, { label: humanize(l), color: LEVEL_COLOR[l] }]));
const FLAG_CONFIG = levelConfig(["REVIEW", "URGENT", "EMERGENCY"]);
const URGENCY_CONFIG = levelConfig(LEVELS);
const PACK_COLORS: DitherColor[] = ["ink", "blue", "purple", "pink"];

const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const weekLabel = (isoWeek: string) => `Week ${Number(isoWeek.split("-W")[1])}`;

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const { data, error } = useApi<Overview>(`/api/analytics?days=${days}`);

  const flags = (data?.flagged_series ?? []).map((d) => ({ ...d, label: dayLabel(d.date) }));
  const hasFlags = flags.some((d) => d.REVIEW + d.URGENT + d.EMERGENCY > 0);

  // One row per week, one column per pack. A pack with no reports in a week carries its last
  // score forward so its line doesn't dive to zero.
  const packs = Object.keys(data?.recovery_trend ?? {});
  const weeks = [...new Set(packs.flatMap((p) => data!.recovery_trend[p].map((r) => r.week)))].sort();
  const trend = weeks.map((week) => ({ week, label: weekLabel(week) }) as Record<string, string | number>);
  for (const p of packs) {
    const byWeek = new Map(data!.recovery_trend[p].map((r) => [r.week, r.avg_score]));
    let last = data!.recovery_trend[p][0]?.avg_score ?? 0;
    for (const row of trend) {
      last = byWeek.get(String(row.week)) ?? last;
      row[p] = last;
    }
  }
  const trendConfig: ChartConfig = Object.fromEntries(
    packs.map((p, i) => [p, { label: humanize(p.replace("_week1", "")), color: PACK_COLORS[i % PACK_COLORS.length] }]),
  );

  const urgency = LEVELS.map((level) => ({ level, count: data?.urgency[level] ?? 0 }));
  const urgencyTotal = urgency.reduce((a, b) => a + b.count, 0);

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Follow-up outcomes across the clinic"
        actions={
          <select
            className="h-9 rounded-lg border border-border bg-surface px-2.5 text-[13px] shadow-[0_1px_1px_rgba(0,0,0,0.03)]"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
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
        <Card title="Flags per day" action={<span className="text-xs text-faint">last 14 days</span>}>
          {data && !hasFlags ? (
            <Empty>No flags in the last 14 days.</Empty>
          ) : (
            <div className="px-4 pb-3 pt-4">
              <BlockLegend config={FLAG_CONFIG} align="end" />
              <div className="mt-2 h-56">
                {data && (
                  <BarChart data={flags} config={FLAG_CONFIG} stackType="stacked" margins={{ left: 28, bottom: 22 }}>
                    <Grid />
                    <YAxis tickCount={4} tickFormatter={(v) => String(Math.round(v))} />
                    <XAxis dataKey="label" maxTicks={7} />
                    {Object.keys(FLAG_CONFIG).map((k) => <Bar key={k} dataKey={k} variant="gradient" />)}
                    <Tooltip labelKey="label" />
                  </BarChart>
                )}
              </div>
            </div>
          )}
        </Card>

        <Card title="Average recovery score" action={<span className="text-xs text-faint">by week, out of 100</span>}>
          {data && trend.length === 0 ? (
            <Empty>No scored reports yet.</Empty>
          ) : (
            <div className="px-4 pb-3 pt-4">
              <BlockLegend config={trendConfig} align="end" />
              <div className="mt-2 h-56">
                {data && (
                  <LineChart data={trend} config={trendConfig} margins={{ left: 28, bottom: 22 }}>
                    <Grid />
                    <YAxis tickCount={4} tickFormatter={(v) => String(Math.round(v))} />
                    <XAxis dataKey="label" maxTicks={6} />
                    {packs.map((p) => <Line key={p} dataKey={p} variant="gradient" />)}
                    <Tooltip labelKey="label" valueFormatter={(v) => v.toFixed(1)} />
                  </LineChart>
                )}
              </div>
            </div>
          )}
        </Card>

        <Card title="Report urgency">
          {data && urgencyTotal === 0 ? (
            <Empty>No reports in this window.</Empty>
          ) : (
            <div className="flex items-center gap-6 px-5 py-5">
              <div className="relative h-40 w-40 shrink-0">
                {data && (
                  <PieChart data={urgency} config={URGENCY_CONFIG} dataKey="count" nameKey="level" innerRadius={0.62}>
                    <Pie variant="gradient" />
                    <Tooltip />
                  </PieChart>
                )}
                <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
                  <div>
                    <div className="text-xl font-semibold tabular-nums">{data ? urgencyTotal : "–"}</div>
                    <div className="text-[11px] text-faint">reports</div>
                  </div>
                </div>
              </div>
              <ul className="flex-1 space-y-2 text-[13px]">
                {urgency.map(({ level, count }) => (
                  <li key={level} className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-[2px]" style={{ background: `var(--${level === "ROUTINE" ? "routine" : level.toLowerCase()})` }} />
                    <span className="text-muted">{humanize(level)}</span>
                    <span className="ml-auto tabular-nums">{count}</span>
                    <span className="w-10 text-right text-xs tabular-nums text-faint">{urgencyTotal ? `${Math.round((count / urgencyTotal) * 100)}%` : ""}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
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

/** Proportion bars that grow in from the left on first paint and glide when the window changes. */
function Breakdown({ values }: { values: Record<string, number> }) {
  const keys = Object.keys(values).sort((a, b) => values[b] - values[a]);
  const total = Object.values(values).reduce((a, b) => a + b, 0) || 1;
  if (keys.length === 0) return <Empty>Nothing in this window.</Empty>;
  return (
    <ul className="space-y-2.5 px-4 py-4">
      {keys.map((k, i) => (
        <li key={k} className="grid grid-cols-[8rem_1fr_2.5rem] items-center gap-3 text-[13px]">
          <span className="truncate text-muted">{humanize(k)}</span>
          <span className="h-1.5 overflow-hidden rounded-full bg-surface-2">
            <span
              className="grow-x block h-full w-full rounded-full bg-accent"
              style={{ "--ratio": values[k] / total, transitionDelay: `${i * 40}ms` } as CSSProperties}
            />
          </span>
          <span className="text-right tabular-nums">{values[k]}</span>
        </li>
      ))}
    </ul>
  );
}
