"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowDownRight, ArrowUpRight, CalendarCheck, Download, Pill as PillIcon, Quote, Shuffle } from "lucide-react";
import { api, useApi } from "@/lib/api";
import { fmtDateTime, fmtValue, humanize } from "@/lib/format";
import type { Call, PatientBrief, Report, Structured } from "@/lib/types";
import { Button, Card, cx, ErrorNote, LEVEL_BAR, LevelBadge, PageHeader, Pill } from "@/components/ui";

type Detail = { report: Report & { structured: Structured }; patient: PatientBrief; call: Call | null; previous_report: Report | null };

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<Detail>(`/api/reports/${id}`);

  const exportFhir = async () => {
    const bundle = await api(`/api/reports/${id}/fhir`);
    const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/fhir+json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `careloop-report-${id}.fhir.json` });
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!data) return <ErrorNote error={error} />;
  const { report: r, patient: p, call } = data;
  const s = r.structured;
  const evidenceTurns = new Set(s.triage.map((t) => t.turn_index).filter((t): t is number => t != null));
  const changes = s.trend?.changes ?? {};

  return (
    <>
      <PageHeader
        title={`${s.pack.name}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <Link href={`/patients/${p.id}`} className="font-medium text-text hover:underline">{p.name}</Link>
            <span>·</span>
            <span>{fmtDateTime(r.created_at)}</span>
            <span>·</span>
            <span>{s.context.doctor}, {humanize(s.context.procedure)}</span>
          </span>
        }
        actions={
          <>
            <LevelBadge level={r.urgency} className="text-sm" />
            {r.status === "partial" && <Pill>partial call</Pill>}
            <Button size="sm" onClick={exportFhir}><Download size={13} /> FHIR</Button>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Summary">
            <p className="px-4 py-3 text-sm leading-relaxed">{r.summary}</p>
          </Card>

          {s.triage.length > 0 && (
            <Card title="Why this was flagged">
              <ul className="divide-y divide-border">
                {s.triage.map((t, i) => (
                  <li key={i} className="flex gap-3 px-4 py-3">
                    <span className={cx("w-1 shrink-0 rounded-full", LEVEL_BAR[t.level])} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <LevelBadge level={t.level} />
                        <span className="font-medium">{t.reason}</span>
                        <span className="text-xs text-faint">{t.source === "lexicon" ? "live red-flag scan" : t.source === "rule" ? `pack rule ${t.rule_id}` : humanize(t.source)}</span>
                      </div>
                      {t.evidence && (
                        <p className="mt-1 flex gap-1.5 text-sm text-muted">
                          <Quote size={13} className="mt-0.5 shrink-0 text-faint" /> {t.evidence}
                        </p>
                      )}
                    </div>
                    {t.turn_index != null && (
                      <a href={`#turn-${t.turn_index}`} className="shrink-0 text-xs text-accent hover:underline">in transcript</a>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title="Answers">
            <div className="grid sm:grid-cols-2">
              {Object.entries(s.answers).map(([key, a]) => (
                <div key={key} className="border-b border-border px-4 py-3 sm:odd:border-r">
                  <div className="text-xs text-muted">{a.question}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className={cx("text-sm font-medium", a.status !== "answered" && "text-faint")}>
                      {a.status === "answered" ? fmtValue(a.value) : humanize(a.status)}
                    </span>
                    {changes[key] && (
                      <span className="text-xs text-faint">was {fmtValue(changes[key].before)}</span>
                    )}
                  </div>
                  {a.evidence && <div className="mt-1 line-clamp-2 text-xs italic text-faint">&ldquo;{a.evidence}&rdquo;</div>}
                </div>
              ))}
            </div>
          </Card>

          <Card title={`Transcript${call ? ` · ${call.mode} call` : ""}`}>
            <div className="space-y-2 px-4 py-4">
              {call?.transcript.length ? (
                call.transcript.map((t, i) => (
                  <div key={i} id={`turn-${i}`} className={cx("flex scroll-mt-20", t.role === "patient" ? "justify-end" : "justify-start")}>
                    <div
                      className={cx(
                        "max-w-[80%] rounded-2xl px-3 py-2 text-sm",
                        t.role === "patient" ? "bg-accent-soft" : "bg-surface-2",
                        evidenceTurns.has(i) && "ring-2 ring-emergency",
                      )}
                    >
                      <div className="mb-0.5 text-[10px] uppercase tracking-wide text-faint">
                        {t.role === "patient" ? "Patient" : "CareLoop"} · {t.t}s
                      </div>
                      {t.text}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-faint">No transcript stored.</p>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card title="Recovery">
            <div className="px-4 py-4">
              <div className="flex items-end gap-2">
                <span className="text-3xl font-semibold tabular-nums">{r.recovery_score ?? "—"}</span>
                <span className="pb-1 text-sm text-faint">/ 100</span>
                {s.trend?.score_delta != null && (
                  <span className={cx("ml-auto flex items-center gap-0.5 text-sm font-medium", s.trend.score_delta >= 0 ? "text-routine" : "text-emergency")}>
                    {s.trend.score_delta >= 0 ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
                    {Math.abs(s.trend.score_delta)} vs last
                  </span>
                )}
              </div>
              {s.trend && (
                <Link href={`/reports/${s.trend.previous_report_id}`} className="mt-2 block text-xs text-accent hover:underline">
                  Previous check-in →
                </Link>
              )}
            </div>
          </Card>

          <Card title="Call">
            <dl className="grid grid-cols-2 gap-y-2 px-4 py-3 text-sm">
              <dt className="text-muted">Language</dt><dd>{s.language}</dd>
              <dt className="text-muted">Consent</dt><dd>{s.consent ? "Given" : s.consent === false ? "Declined" : "—"}</dd>
              <dt className="text-muted">Duration</dt><dd>{Math.round(s.duration_seconds / 60)}m {s.duration_seconds % 60}s</dd>
              <dt className="text-muted">Ended</dt><dd>{humanize(s.end_reason ?? "—")}</dd>
              <dt className="text-muted">Median latency</dt><dd>{s.median_latency_ms ? `${s.median_latency_ms} ms` : "—"}</dd>
            </dl>
          </Card>

          <Card title="Actions taken">
            <ul className="space-y-2 px-4 py-3 text-sm">
              {s.bookings.map((b, i) => (
                <li key={i} className="flex gap-2"><CalendarCheck size={15} className="mt-0.5 shrink-0 text-accent" />{humanize(b.action)} {b.when ?? ""}</li>
              ))}
              {s.department_suggestions.map((d, i) => (
                <li key={`d${i}`} className="flex gap-2"><Shuffle size={15} className="mt-0.5 shrink-0 text-review" />Routed to {humanize(d.department)}: “{d.complaint}”</li>
              ))}
              {s.medications.map((m, i) => (
                <li key={`m${i}`} className={cx("flex gap-2", m.taken !== "all" && "text-urgent")}>
                  <PillIcon size={15} className="mt-0.5 shrink-0" />{m.medication}: {m.taken}{m.reason ? ` (${m.reason})` : ""}
                </li>
              ))}
              {!s.bookings.length && !s.department_suggestions.length && !s.medications.length && (
                <li className="text-faint">None</li>
              )}
            </ul>
          </Card>

          <Card title="Discharge context">
            <dl className="space-y-1.5 px-4 py-3 text-sm">
              <div><dt className="inline text-muted">Clinic: </dt><dd className="inline">{s.context.clinic}</dd></div>
              <div><dt className="inline text-muted">Discharged: </dt><dd className="inline">{s.context.discharged}</dd></div>
              <div><dt className="text-muted">Medicines</dt><dd>{s.context.medications.join(", ") || "—"}</dd></div>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
