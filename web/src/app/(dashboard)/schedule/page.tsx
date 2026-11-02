"use client";

import { useState } from "react";
import { useApi } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/format";
import type { Meta } from "@/lib/types";
import { useLive } from "@/components/Shell";
import { Card, cx, ErrorNote, PageHeader } from "@/components/ui";

type SlotRow = { slot_id: number; doctor: string; doctor_id: number; specialty: string; start: string; status: string; patient_name: string | null };

export default function SchedulePage() {
  const { data: meta } = useApi<Meta>("/api/meta");
  const [doctorId, setDoctorId] = useState<number | null>(null);
  const doctor = doctorId ?? meta?.doctors[0]?.id ?? null;
  const { data, error, reload } = useApi<SlotRow[]>(doctor ? `/api/schedule?days=7&doctor_id=${doctor}` : null);
  useLive((e) => e.type === "booking" && reload());

  const byDay = new Map<string, SlotRow[]>();
  for (const s of data ?? []) {
    const d = fmtDate(s.start);
    byDay.set(d, [...(byDay.get(d) ?? []), s]);
  }

  return (
    <>
      <PageHeader
        title="Schedule"
        subtitle="Slots the voice agent can offer. Bookings made on calls appear live."
        actions={
          <select className="h-9 rounded-lg border border-border bg-surface px-2 text-sm" value={doctor ?? ""} onChange={(e) => setDoctorId(Number(e.target.value))}>
            {meta?.doctors.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.specialty.replace("_", " ")})</option>)}
          </select>
        }
      />
      <ErrorNote error={error} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[...byDay.entries()].map(([day, slots]) => (
          <Card key={day} title={day}>
            <ul className="grid grid-cols-2 gap-1.5 p-3">
              {slots.map((s) => (
                <li
                  key={s.slot_id}
                  className={cx(
                    "rounded-lg border px-2 py-1.5 text-xs",
                    s.status === "free" ? "border-routine/30 bg-routine-soft" : "border-border bg-surface-2 text-muted",
                  )}
                >
                  <div className="font-medium tabular-nums">{fmtTime(s.start)}</div>
                  <div className="truncate">{s.status === "free" ? "Free" : s.patient_name ?? "Booked"}</div>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </>
  );
}
