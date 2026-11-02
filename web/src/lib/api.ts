"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "nurse" | "doctor" | "admin";
export const IDENTITIES: Record<Role, string> = {
  nurse: "nurse.demo",
  doctor: "dr.demo",
  admin: "admin.demo",
};

export function getRole(): Role {
  try {
    const r = localStorage.getItem("careloop.role");
    if (r === "nurse" || r === "doctor" || r === "admin") return r;
  } catch {}
  return "nurse";
}

export function setRole(role: Role) {
  try {
    localStorage.setItem("careloop.role", role);
  } catch {}
}

/** The demo role, read from localStorage after hydration ("nurse" on the server). */
export function useRole(): Role {
  return useSyncExternalStore(
    () => () => {},
    getRole,
    () => "nurse",
  );
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const role = getRole();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-User": IDENTITIES[role],
      "X-Role": role,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function wsUrl(path: string) {
  return API_URL.replace(/^http/, "ws") + path;
}

/** Fetch a JSON endpoint, with a `reload` to refetch after live events. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    api<T>(path)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [path, nonce]);

  return { data, error, loading, reload, setData };
}

export type LiveEvent = { type: string; data: Record<string, unknown> };
const EVENT_TYPES = ["alert", "alert_ack", "alert_assign", "report", "call", "ring", "booking", "answer", "fallback"];

/** Subscribe to the server-sent events stream. Reconnects automatically. */
export function useLiveEvents(onEvent: (e: LiveEvent) => void) {
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource(`${API_URL}/api/events?role=${getRole()}`);
    source.addEventListener("hello", () => setConnected(true));
    source.onerror = () => setConnected(false);
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, (msg) => {
        try {
          handler.current({ type, data: JSON.parse((msg as MessageEvent).data) });
        } catch {}
      });
    }
    return () => source.close();
  }, []);

  return connected;
}
