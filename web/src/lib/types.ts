export type Level = "ROUTINE" | "REVIEW" | "URGENT" | "EMERGENCY";

export type PatientBrief = {
  id: number;
  name: string;
  age: number | null;
  sex: string | null;
  language: string;
  language_name: string;
  codemix: boolean;
  phone: string;
};

export type Alert = {
  id: number;
  call_id: number | null;
  patient_id: number;
  patient_name: string | null;
  level: Level;
  source: string;
  rule_id: string;
  reason: string;
  evidence: string;
  turn_index: number | null;
  created_at: string;
  acked_by: string | null;
  acked_at: string | null;
  assigned_to: string | null;
};

export type Plan = {
  id: number;
  patient_id: number;
  patient_name: string | null;
  pack_id: string;
  due_at: string;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  token: string;
  fallback_sent_at: string | null;
  language: string | null;
};

export type AnswerEntry = { value: unknown; status: string; evidence: string; question: string };

export type TriageEntry = {
  level: Level;
  source: string;
  rule_id: string;
  reason: string;
  evidence: string;
  turn_index: number | null;
};

export type Structured = {
  pack: { id: string; name: string };
  context: {
    patient_name: string;
    age: number | null;
    clinic: string;
    doctor: string;
    specialty: string;
    procedure: string;
    discharged: string;
    medications: string[];
  };
  language: string;
  consent: boolean | null;
  duration_seconds: number;
  answers: Record<string, AnswerEntry>;
  triage: TriageEntry[];
  bookings: { action: string; appointment_id: number; when?: string }[];
  medications: { medication: string; taken: string; reason: string }[];
  department_suggestions: { complaint: string; department: string }[];
  trend: {
    previous_report_id: number;
    previous_score: number | null;
    score_delta: number | null;
    changes: Record<string, { before: unknown; now: unknown }>;
  } | null;
  end_reason: string | null;
  median_latency_ms: number | null;
};

export type Report = {
  id: number;
  call_id: number;
  patient_id: number;
  patient_name: string | null;
  pack_id: string;
  pack_name: string | null;
  status: string;
  urgency: Level;
  summary: string;
  recovery_score: number | null;
  created_at: string;
  structured?: Structured;
};

export type Turn = { role: "assistant" | "patient"; text: string; t: number; lang?: string };

export type Call = {
  id: number;
  plan_id: number;
  patient_id: number;
  mode: string;
  status: string;
  language: string;
  rang_at: string;
  started_at: string | null;
  ended_at: string | null;
  consent_given: boolean | null;
  transcript: Turn[];
  latencies_ms: number[];
};

export type Risk = { score: number; band: "low" | "medium" | "high"; factors: string[]; heuristic: boolean };

export type Meta = {
  voice_enabled: boolean;
  llm_enabled: boolean;
  languages: { code: string; name: string; native: string; voice: string }[];
  packs: { id: string; name: string; specialty: string; procedure_types: string[]; offset_days: number[]; questions: number; red_flags: number }[];
  clinics: { id: number; name: string; kind: string; city: string }[];
  doctors: { id: number; clinic_id: number; name: string; specialty: string }[];
};
