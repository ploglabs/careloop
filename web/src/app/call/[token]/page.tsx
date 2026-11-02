"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ButtonHTMLAttributes } from "react";
import { ChevronDown, Globe, Keyboard, Mic, MicOff, Phone, PhoneOff, Send } from "lucide-react";
import { API_URL, wsUrl } from "@/lib/api";
import { cx } from "@/components/ui";

type Info = {
  first_name: string;
  clinic: string;
  language: string;
  language_name: string;
  languages: { code: string; name: string; native: string }[];
  plan_status: string;
  ringing: boolean;
  answerable: boolean;
  voice_enabled: boolean;
  llm_enabled: boolean;
};

async function fetchInfo(token: string): Promise<Info> {
  const res = await fetch(`${API_URL}/api/call/${token}`);
  if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
  return res.json();
}

// `id` lets a streamed bot bubble be updated in place instead of appended again.
type Line = { id?: string; who: "agent" | "patient" | "system"; text: string };
type Phase = "idle" | "connecting" | "live" | "ended" | "error";

export default function CallPage() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [language, setLanguage] = useState<string>("");
  const [mode, setMode] = useState<"voice" | "text" | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [lines, setLines] = useState<Line[]>([]);

  // Load, then poll for an incoming ring while idle (dashboard "Call now" or the scheduler).
  useEffect(() => {
    if (phase !== "idle") return;
    let alive = true;
    const load = () =>
      fetchInfo(token)
        .then((data) => {
          if (!alive) return;
          setInfo(data);
          setLanguage((l) => l || data.language);
        })
        .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    load();
    const t = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [phase, token]);

  const add = useCallback(
    (l: Line) =>
      setLines((ls) => {
        const i = l.id ? ls.findIndex((x) => x.id === l.id) : -1;
        return i < 0 ? [...ls, l] : ls.map((x, j) => (j === i ? l : x));
      }),
    [],
  );

  const decline = async () => {
    await fetch(`${API_URL}/api/call/${token}/decline`, { method: "POST" });
    setPhase("ended");
    add({ who: "system", text: "Call declined. The clinic will try again later." });
  };

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg p-4">
      <div className="flex h-[min(800px,calc(100dvh-2rem))] w-full max-w-[400px] flex-col overflow-hidden rounded-[28px] border border-border bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
        <header className="flex items-center gap-3 px-6 pb-3 pt-5">
          <span className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo-mark.png" alt="" width={20} height={20} className="h-5 w-5" />
            CareLoop
          </span>
          <span className="ml-auto truncate text-xs text-muted">{info?.clinic}</span>
        </header>

        {error && <p className="mx-5 rounded-xl bg-emergency-soft p-3 text-sm text-emergency">{error}</p>}

        {info && phase === "idle" && !mode && (
          <Incoming info={info} language={language} setLanguage={setLanguage} onAnswer={(m) => setMode(m)} onDecline={decline} />
        )}

        {mode && info && (
          <div className="animate-fade flex min-h-0 flex-1 flex-col">
            {mode === "voice" ? (
              <VoiceCall token={token} info={info} language={language} lines={lines} add={add} phase={phase} setPhase={setPhase} />
            ) : (
              <TextCall token={token} info={info} language={language} lines={lines} add={add} phase={phase} setPhase={setPhase} />
            )}
          </div>
        )}
        {!mode && phase === "ended" && <Transcript lines={lines} />}

        <footer className="px-6 pb-4 pt-2 text-center text-[11px] leading-snug text-faint">
          Automated assistant, not for emergencies. Call 108 · Synthetic demo
        </footer>
      </div>
    </div>
  );
}

function Incoming({ info, language, setLanguage, onAnswer, onDecline }: {
  info: Info; language: string; setLanguage: (l: string) => void; onAnswer: (m: "voice" | "text") => void; onDecline: () => void;
}) {
  if (!info.answerable) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
        <p className="text-base font-medium">You&apos;re all done</p>
        <p className="text-sm text-muted">This check-in is already complete. Thank you, {info.first_name}.</p>
      </div>
    );
  }
  return (
    <div className="flex flex-1 flex-col items-center px-6 pt-6 text-center">
      <span className="inline-flex items-center gap-2 rounded-full bg-surface-2 px-3 py-1 text-xs font-medium text-muted">
        <span className={cx("h-1.5 w-1.5 rounded-full", info.ringing ? "bg-routine" : "bg-faint")} />
        {info.ringing ? "Incoming call" : "Follow-up check-in"}
      </span>

      <div className={cx("mt-10 grid h-28 w-28 place-items-center rounded-full border border-border bg-surface-2 text-text", info.ringing && "animate-ring")}>
        <Phone size={40} strokeWidth={1.75} />
      </div>

      <h1 className="mt-8 text-[22px] font-semibold leading-tight tracking-tight text-balance">{info.clinic}</h1>
      <p className="mt-2 max-w-[280px] text-[15px] leading-relaxed text-muted text-pretty">
        Hi {info.first_name}, a 2-minute check-in on how you are recovering.
      </p>

      <label className="relative mt-8 w-full">
        <span className="sr-only">Language</span>
        <Globe size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="h-12 w-full appearance-none rounded-2xl border border-border bg-surface pl-11 pr-10 text-[15px] text-text outline-none transition-[border-color] duration-150 focus:border-accent"
        >
          {info.languages.map((l) => <option key={l.code} value={l.code}>{l.native} · {l.name}</option>)}
        </select>
        <ChevronDown size={16} className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-muted" />
      </label>

      <div className="mt-auto grid w-full grid-cols-3 pb-6 pt-10">
        <CallAction label="Decline" onClick={onDecline} className="bg-emergency text-white">
          <PhoneOff size={24} />
        </CallAction>
        <CallAction label="Text" onClick={() => onAnswer("text")} className="border border-border bg-surface-2 text-text">
          <Keyboard size={24} />
        </CallAction>
        <CallAction
          label="Answer"
          onClick={() => onAnswer("voice")}
          disabled={!info.voice_enabled}
          title={info.voice_enabled ? undefined : "Voice needs GNANI_API_KEY and LLM_API_KEY on the server"}
          className="bg-accent text-white"
        >
          <Phone size={24} />
        </CallAction>
      </div>
      {!info.voice_enabled && <p className="-mt-2 pb-4 text-xs text-faint">Voice is off on this server. Text works offline.</p>}
    </div>
  );
}

function CallAction({ label, className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button {...props} className="press flex flex-col items-center gap-2 text-xs font-medium text-muted disabled:opacity-40">
      <span className={cx("grid h-16 w-16 place-items-center rounded-full", className)}>{children}</span>
      {label}
    </button>
  );
}

function Transcript({ lines, typing }: { lines: Line[]; typing?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines, typing]);
  return (
    <div className="flex-1 space-y-2.5 overflow-y-auto px-4 py-4 [scrollbar-width:thin]">
      {lines.map((l, i) =>
        l.who === "system" ? (
          <p key={l.id ?? i} className="animate-bubble py-2 text-center text-xs text-faint">{l.text}</p>
        ) : (
          <div key={l.id ?? i} className={cx("flex", l.who === "patient" ? "justify-end" : "justify-start")}>
            <div
              className={cx(
                "animate-bubble max-w-[85%] whitespace-pre-wrap rounded-[20px] px-4 py-2.5 text-[15px] leading-relaxed",
                l.who === "patient" ? "rounded-br-md bg-accent text-white" : "rounded-bl-md bg-surface-2 text-text",
              )}
            >
              {l.text}
            </div>
          </div>
        ),
      )}
      {typing && (
        <div className="flex">
          <div className="typing flex gap-1 rounded-[20px] rounded-bl-md bg-surface-2 px-4 py-3.5">
            <span className="h-1.5 w-1.5 rounded-full bg-muted" />
            <span className="h-1.5 w-1.5 rounded-full bg-muted" />
            <span className="h-1.5 w-1.5 rounded-full bg-muted" />
          </div>
        </div>
      )}
      <div ref={end} />
    </div>
  );
}

function useElapsed(phase: Phase) {
  const started = useRef<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (phase !== "live") return;
    started.current ??= Date.now();
    const t = setInterval(() => setSeconds(Math.floor((Date.now() - started.current!) / 1000)), 1000);
    return () => clearInterval(t);
  }, [phase]);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function CallEnded({ info, elapsed }: { info: Info; elapsed: string }) {
  return (
    <div className="animate-bubble border-t border-border px-6 py-5 text-center">
      <p className="text-sm font-medium">Call ended · {elapsed}</p>
      <p className="mt-1 text-xs text-muted">Thank you, {info.first_name}. Your care team will review this.</p>
    </div>
  );
}

type CallProps = { token: string; info: Info; language: string; lines: Line[]; add: (l: Line) => void; phase: Phase; setPhase: (p: Phase) => void };

function TextCall({ token, info, language, lines, add, phase, setPhase }: CallProps) {
  const ws = useRef<WebSocket | null>(null);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const elapsed = useElapsed(phase);

  useEffect(() => {
    setPhase("connecting");
    const socket = new WebSocket(wsUrl(`/api/call/${token}/text?lang=${language}`));
    ws.current = socket;
    socket.onopen = () => setPhase("live");
    socket.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.type === "typing") setTyping(true);
      if (msg.type === "agent") {
        setTyping(false);
        add({ who: "agent", text: msg.text });
      }
      if (msg.type === "error") add({ who: "system", text: msg.text });
      if (msg.type === "ended") {
        setTyping(false);
        setPhase("ended");
      }
    };
    socket.onclose = () => setPhase("ended");
    return () => socket.close();
  }, [token, language, add, setPhase]);

  const send = (value: string) => {
    if (!value.trim() || ws.current?.readyState !== WebSocket.OPEN) return;
    add({ who: "patient", text: value.trim() });
    ws.current.send(JSON.stringify({ text: value.trim() }));
    setText("");
  };

  return (
    <>
      <Transcript lines={lines} typing={typing} />
      {phase === "ended" ? (
        <CallEnded info={info} elapsed={elapsed} />
      ) : (
        <div className="border-t border-border px-4 pb-2 pt-3">
          <div className="mb-2.5 flex gap-2">
            {["Yes", "No"].map((q) => (
              <button key={q} onClick={() => send(q)} className="press rounded-full border border-border px-4 py-1.5 text-sm text-muted hover:bg-surface-2">{q}</button>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your reply"
              className="h-12 flex-1 rounded-2xl border border-border bg-surface px-4 text-[15px] outline-none transition-[border-color] duration-150 focus:border-accent"
              autoFocus
            />
            <button disabled={!text.trim()} className="press grid h-12 w-12 place-items-center rounded-2xl bg-accent text-white disabled:opacity-40" aria-label="Send">
              <Send size={18} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}

function VoiceCall({ token, info, language, lines, add, phase, setPhase }: CallProps) {
  const client = useRef<import("@pipecat-ai/client-js").PipecatClient | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const [speaking, setSpeaking] = useState<"bot" | "user" | null>(null);
  const [muted, setMuted] = useState(false);
  const elapsed = useElapsed(phase);
  // The bot bubble being filled. Pipecat reports a sentence when it is queued and again when
  // spoken, so sentences are keyed by segment id and each is shown once.
  const bubble = useRef<{ id: string; segments: Map<string, string> } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let n = 0;
    (async () => {
      setPhase("connecting");
      const [{ PipecatClient }, { SmallWebRTCTransport }] = await Promise.all([
        import("@pipecat-ai/client-js"),
        import("@pipecat-ai/small-webrtc-transport"),
      ]);
      const pc = new PipecatClient({
        transport: new SmallWebRTCTransport(),
        enableMic: true,
        enableCam: false,
        callbacks: {
          onConnected: () => setPhase("live"),
          onDisconnected: () => {
            setSpeaking(null);
            setPhase("ended");
          },
          // The server ends the call after its closing line: hang up our side too.
          onBotDisconnected: () => pc.disconnect(),
          onTrackStarted: (track, participant) => {
            if (!participant?.local && track.kind === "audio" && audio.current) {
              audio.current.srcObject = new MediaStream([track]);
              audio.current.play().catch(() => {});
            }
          },
          onBotStartedSpeaking: () => {
            bubble.current = null;
            setSpeaking("bot");
          },
          onBotStoppedSpeaking: () => setSpeaking(null),
          onUserStartedSpeaking: () => setSpeaking("user"),
          onUserStoppedSpeaking: () => setSpeaking(null),
          onUserTranscript: (d) => {
            if (!d.final) return;
            bubble.current = null;
            add({ who: "patient", text: d.text });
          },
          onBotOutput: (d) => {
            const text = d.text?.trim();
            if (!text) return;
            bubble.current ??= { id: `bot-${n++}`, segments: new Map() };
            bubble.current.segments.set(d.segment_id != null ? String(d.segment_id) : text, text);
            add({ id: bubble.current.id, who: "agent", text: [...bubble.current.segments.values()].join(" ") });
          },
          onError: (e) => add({ who: "system", text: `Error: ${JSON.stringify(e.data ?? e)}` }),
        },
      });
      client.current = pc;
      try {
        await pc.connect({ webrtcRequestParams: { endpoint: `${API_URL}/api/call/${token}/offer?lang=${language}` } });
      } catch (e) {
        if (!cancelled) {
          setPhase("error");
          add({ who: "system", text: `Could not start voice: ${e instanceof Error ? e.message : String(e)}` });
        }
      }
    })();
    return () => {
      cancelled = true;
      client.current?.disconnect();
    };
  }, [token, language, add, setPhase]);

  const status =
    phase === "connecting" ? "Connecting…"
    : phase === "error" ? "Couldn't connect"
    : phase === "ended" ? "Call ended"
    : speaking === "bot" ? "Speaking"
    : speaking === "user" ? "Listening"
    : muted ? "Muted" : "Your turn";

  return (
    <>
      <audio ref={audio} autoPlay />
      <div className="flex items-center gap-4 border-b border-border px-6 pb-4 pt-2">
        <div
          className={cx(
            "grid h-14 w-14 shrink-0 place-items-center rounded-full transition-colors duration-200",
            speaking === "bot" ? "bg-accent text-white" : "border border-border bg-surface-2 text-text",
          )}
        >
          <div className={cx("flex h-6 items-center gap-[3px]", speaking === "bot" && "eq")}>
            {[0.5, 0.9, 0.7, 0.4].map((h, i) => (
              <span key={i} className="w-[3px] rounded-full bg-current" style={{ height: `${h * 100}%` }} />
            ))}
          </div>
        </div>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-medium">Care assistant</p>
          <p className="text-sm text-muted">
            <span className={cx(speaking === "user" && "text-text", phase === "error" && "text-emergency")}>{status}</span>
            {phase !== "connecting" && phase !== "error" && <span className="tabular-nums text-faint"> · {elapsed}</span>}
          </p>
        </div>
      </div>

      <Transcript lines={lines} />

      {phase === "live" || phase === "connecting" ? (
        <div className="flex justify-center gap-10 border-t border-border px-6 py-4">
          <CallAction
            label={muted ? "Unmute" : "Mute"}
            disabled={phase !== "live"}
            onClick={() => {
              client.current?.enableMic(muted);
              setMuted(!muted);
            }}
            className={muted ? "bg-text text-surface" : "border border-border bg-surface-2 text-text"}
          >
            {muted ? <MicOff size={22} /> : <Mic size={22} />}
          </CallAction>
          <CallAction label="End" onClick={() => client.current?.disconnect()} className="bg-emergency text-white">
            <PhoneOff size={22} />
          </CallAction>
        </div>
      ) : (
        phase === "ended" && <CallEnded info={info} elapsed={elapsed} />
      )}
    </>
  );
}
