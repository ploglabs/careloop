"use client";

import Link from "next/link";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import type { Meta, Plan } from "@/lib/types";
import { Button, Card, ErrorNote, PageHeader } from "@/components/ui";

export default function IntakePage() {
  const { data: meta, error } = useApi<Meta>("/api/meta");
  const [form, setForm] = useState({ name: "", age: "", language: "hi-IN", codemix: false, doctor_id: "", procedure_type: "", medications: "" });
  const [result, setResult] = useState<{ patient: { id: number; name: string }; plans: Plan[] } | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const doctor = meta?.doctors.find((d) => String(d.id) === form.doctor_id);
  const procedures = meta?.packs.filter((p) => !doctor || p.specialty === doctor.specialty || doctor.specialty === "general_surgery" && p.id === "post_surgery").flatMap((p) => p.procedure_types) ?? [];
  const set = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    try {
      const res = await api<typeof result>("/api/encounters", {
        method: "POST",
        body: JSON.stringify({
          name: form.name, age: form.age ? Number(form.age) : null, language: form.language, codemix: form.codemix,
          doctor_id: Number(form.doctor_id), procedure_type: form.procedure_type,
          medications: form.medications.split(",").map((m) => m.trim()).filter(Boolean),
        }),
      });
      setResult(res);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    }
  };

  const field = "mt-1 h-9 w-full rounded-lg border border-border bg-surface px-3 text-sm";
  return (
    <>
      <PageHeader title="New discharge" subtitle="Record a discharge. Follow-up calls are scheduled from the matching condition pack." />
      <ErrorNote error={error} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <form onSubmit={submit} className="space-y-4 p-4">
            <p className="rounded-lg bg-review-soft px-3 py-2 text-xs text-review">Use invented names only. Real patient data must not be entered in this demo.</p>
            <label className="block text-sm">Patient name<input required className={field} value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm">Age<input type="number" min={0} max={120} className={field} value={form.age} onChange={(e) => set("age", e.target.value)} /></label>
              <label className="block text-sm">Call language
                <select className={field} value={form.language} onChange={(e) => set("language", e.target.value)}>
                  {meta?.languages.map((l) => <option key={l.code} value={l.code}>{l.name} ({l.native})</option>)}
                </select>
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.codemix} onChange={(e) => set("codemix", e.target.checked)} />
              Speaks code-mixed (Hinglish, Tanglish…) → uses Prisma v3.0 auto-detect
            </label>
            <label className="block text-sm">Doctor
              <select required className={field} value={form.doctor_id} onChange={(e) => set("doctor_id", e.target.value)}>
                <option value="">Select…</option>
                {meta?.doctors.map((d) => <option key={d.id} value={d.id}>{d.name} · {humanize(d.specialty)}</option>)}
              </select>
            </label>
            <label className="block text-sm">Procedure
              <select required className={field} value={form.procedure_type} onChange={(e) => set("procedure_type", e.target.value)}>
                <option value="">Select…</option>
                {procedures.map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
              </select>
            </label>
            <label className="block text-sm">Medicines (comma separated)<input className={field} value={form.medications} onChange={(e) => set("medications", e.target.value)} placeholder="Paracetamol 650 mg, Cefuroxime 500 mg" /></label>
            {submitError && <p className="text-sm text-emergency">{submitError}</p>}
            <Button variant="primary" type="submit">Schedule follow-ups</Button>
          </form>
        </Card>
        <Card title="Condition packs">
          <ul className="divide-y divide-border text-sm">
            {meta?.packs.map((p) => (
              <li key={p.id} className="px-4 py-3">
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-muted">
                  Calls on day {p.offset_days.join(" and ")} · {p.questions} questions · {p.red_flags} red-flag rules
                </div>
              </li>
            ))}
          </ul>
          {result && (
            <div className="border-t border-border p-4 text-sm">
              <p className="font-medium">
                Scheduled for <Link className="text-accent hover:underline" href={`/patients/${result.patient.id}`}>{result.patient.name}</Link>:
              </p>
              <ul className="mt-2 space-y-1 text-muted">
                {result.plans.map((pl) => (
                  <li key={pl.id}>
                    {fmtDateTime(pl.due_at)} · <a className="text-accent hover:underline" href={`/call/${pl.token}`} target="_blank" rel="noopener">patient link</a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
