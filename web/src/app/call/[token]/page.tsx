"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Keyboard, Mic, MicOff, Phone, PhoneOff, Send } from "lucide-react";
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

type Line = { who: "agent" | "patient" | "system"; text: string };
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

  const add = useCallback((l: Line) => setLines((ls) => [...ls, l]), []);

  const decline = async () => {
    await fetch(`${API_URL}/api/call/${token}/decline`, { method: "POST" });
    setPhase("ended");
    add({ who: "system", text: "Call declined. The clinic will try again later." });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-4">
      <div className="flex h-[min(780px,calc(100vh-2rem))] w-full max-w-sm flex-col overflow-hidden rounded-[2rem] border border-border bg-surface shadow-xl">
        <header className="flex items-center gap-2 border-b border-border px-5 py-3 text-xs text-muted">
          <Activity size={14} className="text-accent" />
          <span className="font-medium text-text">CareLoop</span>
          <span className="ml-auto truncate">{info?.clinic}</span>
        </header>

        {error && <p className="m-5 rounded-lg bg-emergency-soft p-3 text-sm text-emergency">{error}</p>}

        {info && phase === "idle" && !mode && (
          <Incoming info={info} language={language} setLanguage={setLanguage} onAnswer={(m) => setMode(m)} onDecline={decline} />
        )}

        {mode === "voice" && <VoiceCall token={token} language={language} lines={lines} add={add} phase={phase} setPhase={setPhase} />}
        {mode === "text" && <TextCall token={token} language={language} lines={lines} add={add} phase={phase} setPhase={setPhase} />}
        {!mode && phase === "ended" && <Transcript lines={lines} />}

        <footer className="border-t border-border px-5 py-2 text-center text-[10px] text-faint">
          Automated assistant · not for emergencies, call 108 · synthetic demo
        </footer>
      </div>
    </div>
  );
}

function Incoming({ info, language, setLanguage, onAnswer, onDecline }: {
  info: Info; language: string; setLanguage: (l: string) => void; onAnswer: (m: "voice" | "text") => void; onDecline: () => void;
}) {
  if (!info.answerable) {
    return <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted">This follow-up is already complete. Thank you, {info.first_name}.</div>;
  }
  return (
    <div className="flex flex-1 flex-col items-center px-6 py-8 text-center">
      <p className="text-xs uppercase tracking-widest text-faint">{info.ringing ? "Incoming call" : "Follow-up check-in"}</p>
      <div className={cx("mt-8 grid h-24 w-24 place-items-center rounded-full bg-accent-soft text-accent", info.ringing && "animate-ring")}>
        <Phone size={36} />
      </div>
      <h1 className="mt-6 text-xl font-semibold">{info.clinic}</h1>
      <p className="mt-1 text-sm text-muted">Hi {info.first_name}, a 2-minute check-in on how you are recovering.</p>

      <label className="mt-8 w-full text-left text-xs text-muted">
        Language
        <select value={language} onChange={(e) => setLanguage(e.target.value)} className="mt-1 h-10 w-full rounded-xl border border-border bg-surface px-3 text-sm text-text">
          {info.languages.map((l) => <option key={l.code} value={l.code}>{l.native} · {l.name}</option>)}
        </select>
      </label>

      <div className="mt-auto flex w-full items-end justify-around pt-8">
        <button onClick={onDecline} className="flex flex-col items-center gap-2 text-xs text-muted">
          <span className="grid h-14 w-14 place-items-center rounded-full bg-emergency text-white"><PhoneOff size={22} /></span>
          Decline
        </button>
        <button onClick={() => onAnswer("text")} className="flex flex-col items-center gap-2 text-xs text-muted">
          <span className="grid h-14 w-14 place-items-center rounded-full border border-border bg-surface-2 text-text"><Keyboard size={22} /></span>
          Text
        </button>
        <button
          onClick={() => onAnswer("voice")}
          disabled={!info.voice_enabled}
          title={info.voice_enabled ? undefined : "Voice needs GNANI_API_KEY and LLM_API_KEY on the server"}
          className="flex flex-col items-center gap-2 text-xs text-muted disabled:opacity-40"
        >
          <span className="grid h-14 w-14 place-items-center rounded-full bg-routine text-white"><Phone size={22} /></span>
          Answer
        </button>
      </div>
      {!info.voice_enabled && <p className="mt-3 text-[11px] text-faint">Voice is off on this server (no API keys). Text works offline.</p>}
    </div>
  );
}

function Transcript({ lines, typing }: { lines: Line[]; typing?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [lines, typing]);
  return (
    <div className="flex-1 space-y-2 overflow-y-auto px-4 py-4">
      {lines.map((l, i) =>
        l.who === "system" ? (
          <p key={i} className="py-1 text-center text-xs text-faint">{l.text}</p>
        ) : (
          <div key={i} className={cx("flex", l.who === "patient" ? "justify-end" : "justify-start")}>
            <div className={cx("animate-in max-w-[85%] rounded-2xl px-3 py-2 text-sm", l.who === "patient" ? "rounded-br-sm bg-accent text-white dark:text-black" : "rounded-bl-sm bg-surface-2")}>
              {l.text}
            </div>
          </div>
        ),
      )}
      {typing && <div className="text-xs text-faint">…</div>}
      <div ref={end} />
    </div>
  );
}

type CallProps = { token: string; language: string; lines: Line[]; add: (l: Line) => void; phase: Phase; setPhase: (p: Phase) => void };

function TextCall({ token, language, lines, add, phase, setPhase }: CallProps) {
  const ws = useRef<WebSocket | null>(null);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");

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
        add({ who: "system", text: "Call ended" });
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
      {phase !== "ended" && (
        <div className="border-t border-border p-3">
          <div className="mb-2 flex gap-1.5">
            {["Yes", "No"].map((q) => (
              <button key={q} onClick={() => send(q)} className="rounded-full border border-border px-3 py-1 text-xs text-muted hover:bg-surface-2">{q}</button>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your reply" className="h-10 flex-1 rounded-xl border border-border bg-surface px-3 text-sm" autoFocus />
            <button className="grid h-10 w-10 place-items-center rounded-xl bg-accent text-white dark:text-black" aria-label="Send"><Send size={16} /></button>
          </form>
        </div>
      )}
    </>
  );
}

function VoiceCall({ token, language, lines, add, phase, setPhase }: CallProps) {
  const client = useRef<import("@pipecat-ai/client-js").PipecatClient | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const [speaking, setSpeaking] = useState<"bot" | "user" | null>(null);
  const [muted, setMuted] = useState(false);
  const botOpen = useRef(false);
  const [lastBot, setLastBot] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
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
            setPhase("ended");
            add({ who: "system", text: "Call ended" });
          },
          onTrackStarted: (track, participant) => {
            if (!participant?.local && track.kind === "audio" && audio.current) {
              audio.current.srcObject = new MediaStream([track]);
              audio.current.play().catch(() => {});
            }
          },
          onBotStartedSpeaking: () => {
            botOpen.current = false;
            setSpeaking("bot");
          },
          onBotStoppedSpeaking: () => setSpeaking(null),
          onUserStartedSpeaking: () => setSpeaking("user"),
          onUserStoppedSpeaking: () => setSpeaking(null),
          onUserTranscript: (d) => {
            if (d.final) add({ who: "patient", text: d.text });
          },
          onBotOutput: (d) => {
            if (!d.text?.trim()) return;
            if (!botOpen.current) {
              botOpen.current = true;
              setLastBot(d.text);
              add({ who: "agent", text: d.text });
            } else {
              setLastBot((t) => `${t} ${d.text}`);
            }
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

  // Merge streamed bot output into its bubble.
  const shown = lines.map((l, i) => (i === lines.length - 1 && l.who === "agent" && lastBot ? { ...l, text: lastBot } : l));

  return (
    <>
      <audio ref={audio} autoPlay />
      <div className="flex flex-col items-center gap-2 border-b border-border py-5">
        <div className={cx("grid h-16 w-16 place-items-center rounded-full", speaking === "bot" ? "animate-ring bg-accent text-white dark:text-black" : speaking === "user" ? "bg-routine text-white" : "bg-accent-soft text-accent")}>
          <Activity size={26} />
        </div>
        <p className="text-xs text-muted">
          {phase === "connecting" ? "Connecting…" : phase === "live" ? (speaking === "bot" ? "CareLoop is speaking" : speaking === "user" ? "Listening…" : "Connected") : phase === "error" ? "Couldn't connect" : "Call ended"}
        </p>
      </div>
      <Transcript lines={shown} />
      {phase === "live" && (
        <div className="flex justify-center gap-6 border-t border-border p-4">
          <button
            onClick={() => {
              client.current?.enableMic(muted);
              setMuted(!muted);
            }}
            className="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface-2"
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted ? <MicOff size={20} /> : <Mic size={20} />}
          </button>
          <button onClick={() => client.current?.disconnect()} className="grid h-12 w-12 place-items-center rounded-full bg-emergency text-white" aria-label="Hang up">
            <PhoneOff size={20} />
          </button>
        </div>
      )}
    </>
  );
}
