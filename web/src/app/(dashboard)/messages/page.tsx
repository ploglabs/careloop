"use client";

import { MessageCircle, MessageSquareText, Pill, Siren } from "lucide-react";
import { useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useLive } from "@/components/Shell";
import { Card, Empty, ErrorNote, PageHeader } from "@/components/ui";

type Msg = { id: number; channel: string; recipient: string; body: string; created_at: string };

const ICON = { whatsapp: MessageCircle, sms: MessageSquareText, nurse_alert: Siren, pharmacy: Pill } as const;
const LABEL: Record<string, string> = { whatsapp: "WhatsApp", sms: "SMS", nurse_alert: "Nurse alert", pharmacy: "Pharmacy" };

export default function MessagesPage() {
  const { data, error, reload } = useApi<Msg[]>("/api/outbox");
  useLive((e) => ["alert", "fallback", "report"].includes(e.type) && reload());
  return (
    <>
      <PageHeader title="Messages" subtitle="Outbound alerts and fallback messages. Simulated: nothing is actually sent in the demo." />
      <ErrorNote error={error} />
      <Card>
        {data?.length === 0 && <Empty>No messages yet.</Empty>}
        <ul className="divide-y divide-border">
          {data?.map((m) => {
            const Icon = ICON[m.channel as keyof typeof ICON] ?? MessageSquareText;
            return (
              <li key={m.id} className="flex gap-3 px-4 py-3">
                <Icon size={16} className="mt-0.5 shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-faint">
                    <span className="font-medium text-text">{LABEL[m.channel] ?? m.channel}</span>
                    <span>to {m.recipient}</span>
                    <span className="ml-auto">{fmtDateTime(m.created_at)}</span>
                  </div>
                  <p className="mt-1 break-words text-sm">{m.body}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}
