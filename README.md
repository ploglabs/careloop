# CareLoop

A post-discharge care layer for clinics and hospital chains. A multilingual voice agent calls patients after they leave, runs a condition-specific check-in, triages what it hears in real time, books follow-up visits during the call, and hands the care team a structured report.

Built for the Gnani AI Great Indian AI Internship Challenge, on **Gnani Prisma** (speech-to-text) and **Gnani Timbre** (text-to-speech).

> All data in this repository and its demos is synthetic. No real patients, phone numbers, IDs or recordings are used.

## What it does

**1. Check-in, timed to the procedure**
- Day 1 and day 7 after surgery, day 7 for dermatology, day 30 for chronic care.
- Questions come from YAML condition packs (`backend/src/careloop/packs/`), so the output is typed data rather than a vague transcript. For example, derma asks about redness trend, itching 0-10, swelling, spread, fever and medicine adherence.
- The call opens with a consent disclosure in the patient's language. No health answer can be stored until consent is recorded.

**2. Triage that can only raise urgency**

| Layer | When it runs | What it does |
|---|---|---|
| Red-flag lexicon | Every final transcript, all 10 languages plus romanised Hinglish | Clause-aware negation ("no fever" is not a flag). A negated *emergency* phrase is downgraded to REVIEW, never dropped. |
| Pack rules | After each typed answer | Deterministic expressions such as `swelling and fever → URGENT` or `pain_score >= 8 → URGENT` |
| LLM review | End of call | Clinician summary plus a second opinion that can raise the level, never lower it |

- On URGENT or EMERGENCY, the scripted safety line is spoken verbatim in the patient's language, with no LLM improvisation.
- A nurse alert is raised and pushed live to the dashboard.
- Every alert records the rule that fired and the patient's own words.

**3. Action**
- In-call booking, rescheduling and cancelling against real slots, using an atomic claim so concurrent calls can't double-book.
- Routing to another department when the complaint doesn't match the original specialty.
- Per-medicine adherence tracking, with a doctor and pharmacy flag after repeated misses.
- No answer: retry, then fall back to a WhatsApp/SMS link that opens the same check-in by voice or text.

**Clinic dashboard**
- Live alert queue with acknowledge and assign.
- "12 patients flagged this week" view with filters.
- Per-call report: why it was flagged, answers with change since the last check-in, and the transcript with the triggering turn highlighted.
- Recovery trends, analytics, schedule, a simulated outbox, and a discharge intake form.
- FHIR R4 export (`QuestionnaireResponse` and `Observation`) plus CSV for HIS/EMR import.

## Gnani models used

| Purpose | Model | How |
|---|---|---|
| Speech-to-text | **Prisma v2.5**, pinned to the patient's language | Realtime WebSocket via `pipecat-gnani` `GnaniSTTService` |
| Speech-to-text, code-mixed callers | **Prisma v3.0** with `indic-auto` and `language_candidates=[lang, en-IN]`, plus keyword hints (doctor and medicine names) | Same service |
| Text-to-speech | **Timbre v2.5**, one voice per language (Poorvi for Hinglish) | Realtime WebSocket `GnaniTTSService`, with barge-in |
| Evaluation | Prisma REST and Timbre REST through the `gnani-vachana` SDK | `backend/eval/run_eval.py` |

Dialogue runs on an OpenAI-compatible tool-calling LLM: DeepInfra `google/gemma-4-26B-A4B-it` by default, chosen after comparing DeepInfra models for latency, tool-call accuracy and Hindi output on the real call prompt. Evon is not available on the API, so it is not used.

## Languages

English, Hindi, Bengali, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Tamil, Telugu: the 10 languages Prisma and Timbre support. Code-mixed Hinglish, Tanglish and Benglish speech goes through Prisma v3.0.

The safety lines and red-flag lexicon are written for all 10. A language counts as *supported* only after `eval/run_eval.py languages` passes and a native speaker has reviewed it.

| Language | Safety lines | Lexicon tests | Voice round trip | Native review |
|---|---|---|---|---|
| English | ✅ | ✅ | ✅ | pending |
| Hindi / Hinglish | ✅ | ✅ | ✅ | pending |
| Tamil, Kannada | ✅ | ✅ | ✅ | pending |
| Telugu, Malayalam, Marathi, Bengali, Gujarati, Punjabi | ✅ | ✅ (basic) | ✅ | pending |

### Speech round trip (Timbre v2.5 → Prisma v2.5)

Each scripted line is synthesised by Timbre and transcribed back by Prisma (`eval/run_eval.py languages`). CER is the character error rate against the script.

| Language | Consent line CER | Emergency line CER | Timbre TTS | Prisma STT |
|---|---|---|---|---|
| English (en-IN) | 0.036 | 0.0 | ok | ok |
| Hindi (hi-IN) | 0.183 | 0.0 | ok | ok |
| Bengali (bn-IN) | 0.176 | 0.035 | ok | ok |
| Gujarati (gu-IN) | 0.175 | 0.0 | ok | ok |
| Kannada (kn-IN) | 0.154 | 0.0 | ok | ok |
| Malayalam (ml-IN) | 0.17 | 0.039 | ok | ok |
| Marathi (mr-IN) | 0.175 | 0.055 | ok | ok |
| Punjabi (pa-IN) | 0.185 | 0.025 | ok | ok |
| Tamil (ta-IN) | 0.152 | 0.0 | ok | ok |
| Telugu (te-IN) | 0.2 | 0.025 | ok | ok |

The emergency line, the one that must be understood, comes back almost word for word in every language. Most of the consent line's error is the clinic, doctor and patient names: the script writes them in English ("Dr. Rao") and Prisma correctly writes them in the native script ("डॉक्टर राव"), which counts as a mismatch.

## Architecture

```
 Patient (browser /call/<token>)            Clinic dashboard (Next.js)
     │ WebRTC audio   │ or text (WS)             ▲ REST + server-sent events
     ▼                ▼                          │
 ┌──────────────────────────────┐     ┌──────────┴───────────┐
 │ Pipecat pipeline              │     │ FastAPI              │
 │  Prisma STT → TriageTap →     │────▶│  patients, reports,  │◀── APScheduler
 │  LLM (tools) → Timbre TTS     │     │  alerts, slots, FHIR │    ring / retry /
 └──────────────┬───────────────┘     └──────────┬───────────┘    fallback
                │ CallSession (tools, triage, consent)│
                └──────────────► SQLite / Postgres ◄──┘
```

| Path | Contents |
|---|---|
| `backend/src/careloop/agent/` | `session.py` (call state and tools), `voice.py` (Pipecat + Gnani), `brain.py` (text LLM loop and end-of-call review), `offline.py` (keyword brain so everything runs without keys) |
| `backend/src/careloop/triage/` | Lexicon, rule evaluator, engine |
| `backend/src/careloop/packs/` | Condition packs (YAML) |
| `backend/src/careloop/languages.py` | Language list, voices, scripted safety lines |
| `backend/eval/` | Labelled triage cases and the speech/noise evaluation |
| `web/` | Dashboard and patient call page |

## Running it

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+ with pnpm.

```bash
# Backend
cd backend
cp .env.example .env        # add GNANI_API_KEY and LLM_API_KEY for voice; text mode works without
uv sync
uv run careloop seed        # synthetic clinics, patients, slots, and past check-ins
uv run careloop serve       # http://localhost:8000

# Dashboard
cd web
cp .env.example .env.local
pnpm install
pnpm dev                    # http://localhost:3000
```

On the **Today** board, press **Call now** on any follow-up. The patient's phone page opens; answer by voice (needs keys) or by text.

Without an LLM key, text calls use the offline keyword brain (English only). Use it for development and as a fallback; the multilingual experience needs the LLM.

```bash
uv run pytest                                   # 75 tests: triage cases, call flows, booking races, API
uv run careloop simulate 3 yes 2 better no ...  # scripted synthetic call from the terminal
uv run python eval/run_eval.py languages        # per-language Timbre → Prisma round trip
uv run python eval/run_eval.py noise            # triage at 16 kHz, 8 kHz phone, 8 kHz + noise (SNR 10/5 dB)
```

## Privacy and compliance (DPDP Act 2023)

- **Consent:** spoken disclosure at call start (who is calling, AI handling, purpose), logged per call. Withdrawal stops all future calls.
- **Minimisation:** raw audio is not stored (`CARELOOP_STORE_AUDIO=0`). The record is typed answers, evidence quotes and the transcript.
- **Access:** care-team roles only, and every report view or export is written to the audit log (admin view).
- **Erasure:** an admin endpoint strips transcripts, quotes and identity, keeping only de-identified aggregates.
- **Production path:** India-region hosting, encryption at rest, a DPA with the hospital as data fiduciary, SSO in place of the demo role headers, and Gnani's on-prem Artha stack for sovereign deployments.

## Built vs roadmap

**Built:**
- Voice and text calls, 10-language safety scripts, 3-layer triage, booking/reschedule/cancel/routing, adherence flags.
- Retry and fallback, reports, FHIR/CSV export, dashboard, analytics, consent/audit/erasure, evaluation harness.

**Roadmap (not in this demo):**
- Real PSTN telephony (Exotel or Ozonetel) and WhatsApp Business delivery. The demo deliberately uses web calls and a simulated outbox.
- Live HIS/EMR connectors and ABDM linkage.
- A validated readmission-risk model; today's score is a labelled heuristic.
- Clinician-authored packs for more specialties.
