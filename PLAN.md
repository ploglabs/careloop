# CareLoop: Implementation Plan

Post-discharge care layer for clinics and hospital chains. A multilingual voice agent that does three jobs: **check-in → triage → action**.

Built for the Gnani AI "Great Indian AI Internship Challenge". Final submission closes **Nov 10, 2026, 11:59 PM IST**. Today is Nov 2, so there are **8 days**, and the plan is scoped to that.

---

## 1. Constraints from the Gnani brief

| Constraint | Consequence for the build |
|---|---|
| Must run on Gnani models/APIs and name them in the submission | Prisma (STT) and Timbre (TTS) are the core. State each teammate's contribution. |
| **Synthetic data only.** No real phone numbers, Aadhaar, PAN, or recorded calls | No live PSTN calls to real people. Demo via **web call link** to simulated patients. Synthetic patient seed data. Telephony is a documented production path, not a demo dependency. |
| Agent Builder is out of scope, no APIs | We orchestrate ourselves, using Pipecat plus the official `pipecat-gnani` adapter. |
| Evon v3.3 LLM is open-weight only, not on the API | Use a hosted LLM for dialogue (Groq/Llama or Claude API). Mention Evon as the sovereign-deployment option. Do not depend on it. |
| Public demo on LinkedIn/X with `#GnaniAI #GreatIndianAIInternshipChallenge`, tagging Gnani, live before submission | Reserve Nov 8-9 for the video and post. |
| 5,000 programme credits per participant | Budget calls: cache TTS for static lines, keep test calls short, avoid looping streams. |

**Award categories to aim at** (pick 3-4 to optimise for):
- **Real Deal**: real hospital workflow. This is the natural fit.
- **Main Character**: regional language depth (Kannada/Tamil/Telugu done well).
- **Mixed Vibes**: Hinglish/Tanglish code-mix via Prisma v3.0.
- **Noise Canceller**: 8 kHz noisy telephonic audio test.
- **Demo Day Drop**: 60-second video.

---

## 2. Gnani capabilities (verified from docs.gnani.ai)

- **Base URL** `https://api.vachana.ai`, auth header `X-API-Key-ID`. Keys from `app.gnani.ai/voice`.
- **STT, Prisma**
  - v2.5 (default): transcribes in the specified language.
  - v3.0 (`prisma-v3.0`): multilingual with auto-detect (`indic-auto`), and `codemix`/`transliterate` formats.
  - REST (≤30 s), WebSocket realtime (raw PCM, 8/16/44.1/48 kHz), and batch.
  - P95 ≈ 200 ms.
- **TTS, Timbre v2.5** (v3.0 also listed)
  - REST, SSE, and WebSocket (the WebSocket supports barge-in).
  - Speed 0.85-1.15, SSML supported, voice catalog, zero-shot voice cloning.
- **Languages (10):** `en-IN, hi-IN, bn-IN, gu-IN, kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN`.
  - **Odia/Assamese are not in the Pipecat adapter's STT/TTS list.**
  - The pitch says "10+ languages incl. English". Gnani's 10 already include English, so say **"10 Indian languages + code-mixed Hinglish/Tanglish/Benglish"** and don't claim more.
- **Integration:** `pip install pipecat-gnani` (needs Python 3.11+, Pipecat ≥1.5,<2.0, `gnani-vachana ≥0.9.0`). Classes: `GnaniSTTService`, `GnaniTTSService`, plus HTTP/SSE variants. Env var: `GNANI_API_KEY`. A LiveKit integration also exists.
- **Not documented, verify on Day 1:** rate limits, exact voice list per language, and whether Prisma v3.0 works over the realtime WebSocket (the adapter lists `model` as a setting for both).

---

## 3. Product scope

### Must ship (the demo is judged on this)
1. Scheduled check-in call, timed by procedure type.
2. Condition-specific structured capture (2 packs: **Derma** and **Post-surgery**; a 3rd, **Chronic/diabetes**, if time).
3. Deterministic **triage** with real-time escalation (the headline feature).
4. In-call **booking, reschedule, and cancel** against a slots table.
5. Structured report per call, plus a **clinic dashboard** (flagged patients, urgency queue, per-patient report).
6. 5+ languages demonstrably working; all 10 selectable.
7. Consent disclosure at call start and a DPDP-aware data model.

### Should ship if time allows
- No-answer retry plus a simulated WhatsApp/SMS fallback with a link to a short voice/form check-in.
- Medication adherence tracking across calls, with a pharmacy/doctor flag after N misses.
- Cross-specialty routing (the derma patient reports chest pain, so the agent says "go to emergency" and flags it).
- FHIR-shaped JSON export, as the "EMR/HIS integration" story.

### Pitch-only (slide or README, not built)
- Readmission-risk scoring, satisfaction trends, and the analytics layer (a simple heuristic score is OK).
- Real HIS connectors (HL7/FHIR to Practo/HealthPlix/Epic), real telephony (Exotel/Twilio/Ozonetel), and the Artha/on-prem deployment.
- Full HIPAA/ABDM alignment.

---

## 4. Architecture

```
                 ┌─────────────────────────────────────────────┐
                 │               Clinic Dashboard (Next.js)     │
                 │  flagged queue · patient report · analytics  │
                 └──────────────▲──────────────────────────────┘
                                │ REST + SSE (live alerts)
┌───────────┐   ┌───────────────┴───────────────┐    ┌──────────────┐
│ Scheduler │──▶│        API / Orchestrator      │◀──▶│  Postgres/   │
│ (APScheduler│  │  FastAPI: patients, calls,     │    │  SQLite      │
│  / cron)   │   │  slots, reports, alerts        │    └──────────────┘
└───────────┘   └───────┬───────────────▲───────┘
                        │ start session │ tool calls
                ┌───────▼───────────────┴───────┐
 Patient  ◀────▶│  Voice Agent (Pipecat pipeline)│
 (web call)     │  transport → VAD → Prisma STT  │
                │  → LLM (tools) → Timbre TTS    │
                └──────────────┬─────────────────┘
                               │ transcript + tool log
                        ┌──────▼───────┐
                        │ Post-call    │  extract → rules triage → report
                        │ pipeline     │  → alert → FHIR export
                        └──────────────┘
```

### Stack
| Layer | Choice | Why |
|---|---|---|
| Voice runtime | **Pipecat** + `pipecat-gnani` | Official Gnani adapter, barge-in via WebSocket TTS, swappable transport |
| Transport (demo) | Pipecat SmallWebRTC (browser call page) | No telephony, no real numbers, satisfies the synthetic-data rule |
| LLM | Hosted (Groq Llama 3.3 70B for speed, or Claude for quality; benchmark both on Day 2) | Low-latency tool calling. Evon is not API-available. |
| Backend | FastAPI + SQLModel | Fast to build, async-friendly |
| DB | SQLite → Postgres | SQLite for the hackathon, schema Postgres-compatible |
| Scheduler | APScheduler | Enough for demo; Temporal/Celery in production |
| Dashboard | Next.js + Tailwind + shadcn | Quick, good-looking |
| Live alerts | SSE from FastAPI | Simpler than websockets for one-way push |

### Repo layout
```
careloop/
  agent/           # Pipecat pipeline, prompts, tools, language config
    pipeline.py
    tools.py          # record_answer, escalate, check_slots, book/reschedule/cancel, end_call
    prompts/          # base system prompt + per-language style notes
    packs/            # derma.yaml, post_surgery.yaml, chronic.yaml
  api/             # FastAPI app, models, routers, scheduler
  triage/          # rules engine + tests
  reports/         # extraction, summary, FHIR export
  web/             # Next.js dashboard + /call/[token] patient call page
  seed/            # synthetic patients, doctors, slots
  eval/            # scripted test calls, noisy-audio tests, triage test suite
  PLAN.md  README.md
```

---

## 5. Key design decisions

### 5.1 Condition packs (data, not code)
Each pack is YAML so adding a specialty means no code change:

```yaml
id: derma_week1
trigger: { specialty: derma, offset_days: 7 }
questions:
  - key: redness_trend     # better | same | worse
  - key: itching_score     # 0-10
  - key: swelling          # bool
  - key: new_rash_spread   # bool
  - key: med_adherence     # all | some | none (+ reason)
  - key: side_effects      # free text -> normalised list
red_flags:
  - { when: "swelling && fever", level: URGENT }
  - { when: "new_rash_spread && breathing_difficulty", level: EMERGENCY }
  - { when: "itching_score >= 8", level: REVIEW }
```

Check-in timing is by procedure: surgery day 1 (+ day 7), derma day 7, chronic day 30. The `offset_days` lives on the pack.

### 5.2 Conversational but structured
- The LLM drives natural conversation, but each pack question must resolve to a typed value via the `record_answer(key, value, confidence, evidence_quote)` tool.
- The agent tracks `unanswered_keys` in its prompt state and doesn't end the call until each is answered or marked `declined`/`unclear`.
- Keep turns short: one question at a time, ≤2 sentences, and confirm numerals ("pain 7 out of 10, correct?").

### 5.3 Triage: deterministic rules over LLM judgement
**This is the differentiator, so it must be reliable and explainable.**
1. **Layer 1, keyword/red-flag lexicon** per language, run on every STT final transcript in real time (chest pain, can't breathe, heavy bleeding, pus, faint, etc.). A hit triggers an immediate `escalate()`.
2. **Layer 2, pack rules** over the structured answers (the `red_flags` above), evaluated after each `record_answer`.
3. **Layer 3, LLM second opinion** at call end, which can only *raise* urgency, never lower it.
4. Levels: `ROUTINE → REVIEW → URGENT → EMERGENCY`. For URGENT/EMERGENCY, the agent:
   - says a scripted safe-response in the patient's language (no improvisation),
   - creates an alert (SSE to the dashboard, plus a simulated nurse call/WhatsApp),
   - offers the earliest slot or tells them to go to the ER.
5. Every alert stores *why* it fired: rule id, evidence quote, and the timestamp in the transcript.
6. The agent never diagnoses or advises on medication changes. It states it is an automated assistant.

### 5.4 Multilingual
- Language comes from the patient profile. The agent greets in that language and offers a switch ("हिंदी / English?").
- STT: Prisma v2.5 pinned to the profile language by default. For code-mixed callers, use **Prisma v3.0 with `indic-auto` plus `language_candidates=[profile_lang, en-IN]`**. The docs warn that bare auto-detect can mis-detect on trailing silence.
- TTS: Timbre v2.5, with the voice chosen per language from the voice catalog (confirm the catalog on Day 1).
- LLM prompt is in English, with a per-language style note. Output is in the target language in native script, and **numbers and doctor names are normalised for TTS** (Timbre handles lakh/crore and Indian names).
- **Quality gate:** native-speaker spot checks for at least Hindi, Tamil, and Kannada. Don't ship a language that wasn't tested end to end.
- Report fields are stored in English (normalised) plus the original-language transcript.

### 5.5 Booking
- `check_slots(doctor|specialty, date_range)` returns the next 3 slots, and the agent offers at most 3 at a time.
- `book_slot`, `reschedule`, and `cancel` run in a transaction. Slot conflicts are re-checked at write time, so two parallel calls can't double-book.
- Read-back confirmation ("Tuesday, 4 PM, Dr. Rao. Confirm?") before commit.
- Re-routing: if a complaint doesn't match the original specialty, `suggest_department()` picks from a small map, and the report records the reason.

### 5.6 Consent and compliance (DPDP Act 2023)
- Call opens with a short disclosure in the patient's language: who is calling, that it's an automated assistant, purpose, and recording/AI processing. It asks "Is it OK to continue?" and ends gracefully on no.
- `consents` table: patient id, purpose, language, timestamp, channel, and withdrawal status.
- Minimise data: store the structured report plus the transcript, and make audio retention configurable (default **off** for the demo).
- Role-based dashboard access, an audit log of who viewed which report, and a retention/erasure job (documented, stubbed).
- Production notes for the README: India-region hosting, encryption at rest, a DPA with the hospital as data fiduciary, ABDM alignment, and the Gnani Artha on-prem option for sovereign deployments.

### 5.7 Reliability and call handling
- Barge-in via the WebSocket TTS. VAD tuning for slow speakers and elderly patients (longer end-of-speech timeout).
- "Did you say X?" fallback after 2 low-confidence STT turns, then a human-callback offer on a third failure.
- Retry policy: up to 3 attempts across time windows, then the simulated WhatsApp link. The state machine is `scheduled → ringing → connected | no_answer → retry → fallback → closed`.
- Hard guard: max call length (e.g. 6 min), and the report is always produced, even on a dropped call (`status=partial`).

---

## 6. Data model

```
clinics(id, name, type[chain|clinic], timezone)
doctors(id, clinic_id, name, specialty)
patients(id, clinic_id, name, phone_synthetic, language, age, ...)
consents(id, patient_id, purpose, granted_at, withdrawn_at, channel)
encounters(id, patient_id, doctor_id, procedure_type, discharged_at, meds[])
followup_plans(id, encounter_id, pack_id, due_at, status, attempts)
calls(id, plan_id, started_at, ended_at, status, language_used, transcript_json)
answers(id, call_id, key, value, confidence, evidence_quote, turn_ts)
triage_events(id, call_id, level, rule_id, evidence, created_at, acked_by, acked_at)
reports(id, call_id, summary_en, structured_json, urgency, fhir_json)
slots(id, doctor_id, start, end, status[free|held|booked], patient_id)
appointments(id, slot_id, patient_id, reason, source[voice_agent|manual])
med_adherence(id, patient_id, med, date, taken, reason)
audit_log(id, actor, action, entity, entity_id, at)
```

---

## 7. Dashboard

1. **Today board:** counts (calls done, no-answer, flagged), and a live urgent queue with ack/assign buttons. SSE pushes a new alert with a sound/toast.
2. **Patient report page:** structured answers, a trend vs. the previous check-in, the transcript with the triggering turn highlighted, and booking outcome.
3. **Flagged list:** "12 patients flagged this week", filterable by specialty, doctor, urgency, and language.
4. **Analytics (light):** adherence rate, average recovery score trend, and a heuristic readmission-risk badge. Label it clearly as heuristic.
5. **Export:** FHIR `QuestionnaireResponse`/`Observation` JSON and PDF/CSV per report.
6. **Patient call page** (`/call/[token]`): the "ring" simulation. It opens the web call, is also the target of the fallback link, and doubles as the demo surface.

---

## 8. Timeline (Nov 2 → Nov 10)

| Day | Date | Goals | Exit criteria |
|---|---|---|---|
| 1 | Nov 2 | Register, get API key. Read the STT/TTS/voices docs. Scaffold the repo. Run the `pipecat-gnani` example end to end in Hindi and English. | Voice loop works with the browser. Voice and rate-limit facts recorded in the README. |
| 2 | Nov 3 | DB schema and seed data. Pack loader. Agent with `record_answer` and the derma pack in English and Hindi. LLM benchmark (latency and tool-call reliability). | One full derma call writes structured answers to the DB. |
| 3 | Nov 4 | Triage engine (lexicon, rules, tests). Escalation flow and alerts via SSE. Post-surgery pack. | Scripted red-flag calls reliably produce EMERGENCY/URGENT alerts. Triage unit tests pass. |
| 4 | Nov 5 | Booking tools (check, book, reschedule, cancel, re-route). Consent flow. Report generator. | The voice call books and reschedules a slot, and the DB reflects it. |
| 5 | Nov 6 | Dashboard: Today board, patient report, flagged list. Scheduler and retry state machine. | End-to-end: scheduled → call → report → dashboard alert. |
| 6 | Nov 7 | Languages: enable all 10, tune prompts, native-speaker checks (Tamil, Kannada, Telugu, Hindi). Code-mix with Prisma v3.0. Noisy 8 kHz test. | Language matrix filled with pass/fail. |
| 7 | Nov 8 | Should-ship items (fallback link, adherence, FHIR export, analytics). **Feature freeze at end of day.** Bug fixes. | Demo script rehearsed twice with no crashes. |
| 8 | Nov 9 | Record the 60 s demo and a longer walkthrough. README, architecture diagram, model-usage and contribution statement. Publish the LinkedIn/X post (tag Gnani, both hashtags). | Post is live and public. |
| 9 | Nov 10 | Buffer, submission form (nominate the post). Submit **before evening**. | Submitted, with confirmation saved. |

With 8 days, the cut line is: **drop analytics and FHIR before touching triage, booking, or language quality.**

---

## 9. Testing and evaluation

- **Triage suite:** 40+ labelled utterances across languages (clear red flags, negations like "no fever", ambiguous). Target: **zero false negatives on EMERGENCY cases**; tolerate some over-flagging.
- **Language matrix:** for each language, the same scripted patient is run through greeting → 3 answers → booking, and logs WER spot-checks and TTS pronunciation of names/numerals.
- **Noise test:** downsample to 8 kHz, add background (traffic, clinic ambience, speakerphone), and compare structured-answer accuracy with and without noise. This is useful material for the Noise Canceller category.
- **Latency:** log STT-final → first TTS byte per turn. Target p50 < 1.2 s, and show the numbers in the README.
- **Booking concurrency:** two simulated calls race for the same slot, and exactly one wins.
- **Synthetic callers:** use scripted TTS "patient" audio or a second LLM playing the patient, so tests don't involve real people or real recordings.

---

## 10. Demo script (60 s video, plus a longer walkthrough)

1. (0-8 s) Dashboard: "Clinic discharged 40 patients this week." A Kannada derma follow-up kicks off.
2. (8-25 s) Short live call in Tamil or Kannada: the patient says redness is worse and mentions fever. Captions show the structured capture.
3. (25-40 s) The agent escalates in-call, and the **dashboard alert pops live** with the quote and the rule that fired.
4. (40-52 s) A second, calmer call in Hinglish: the patient wants to see the doctor, and the agent books a slot that then appears on the schedule.
5. (52-60 s) Closing card: 10 languages · built on Gnani Prisma + Timbre · DPDP-aware.

---

## 11. Submission checklist

- [ ] Registered; API key stored in `.env`, not committed
- [ ] Models/APIs named: Prisma v2.5/v3.0 (STT), Timbre v2.5 (TTS), plus the LLM used
- [ ] Each teammate's contribution written down (if a team of two)
- [ ] Only synthetic data anywhere (seed, demo, screenshots, recordings)
- [ ] Public LinkedIn/X post live, with `#GnaniAI #GreatIndianAIInternshipChallenge` and a Gnani tag, and nominated in the form
- [ ] 60 s demo video
- [ ] Repo README: architecture, setup, language matrix, latency and noise numbers, limitations
- [ ] No purchased engagement, bots, or engagement swaps (disqualifying)
- [ ] Submitted before Nov 10, 11:59 PM IST (aim for Nov 10 afternoon)

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| 8-day window | Hard scope tiers in §3, feature freeze Day 7 |
| Credits run out (5,000) | Cache static TTS lines, text-mode testing for logic, limit long calls |
| LLM mishears or hallucinates a medical answer | Typed tools with evidence quotes, read-back confirmation, deterministic triage, no medical advice |
| A language is weak | Ship only tested languages as "supported", list the others as "available, in validation" |
| Latency spikes | WebSocket STT/TTS, a fast LLM, short prompts, filler phrases ("one moment…") during tool calls |
| Prisma v3.0 realtime support unclear | Check on Day 1. Fall back to v2.5 pinned per patient language. |
| Pitch overclaims (HIPAA, EMR integration, 10+ languages) | Say what is built vs. roadmap. Judges check for "misleading demos". |
| Telephony temptation | Keep the demo on web calls. Real numbers break the synthetic-data rule. |

---

## 13. Post-hackathon roadmap (for the pitch)

1. Real telephony (Exotel/Ozonetel) and WhatsApp Business flows.
2. HIS/EMR connectors via FHIR/HL7 and ABDM (ABHA) linkage.
3. More condition packs (cardiac, ortho, maternity, oncology follow-up), built by clinicians.
4. Analytics: readmission risk model trained on outcomes, and NPS/satisfaction trends.
5. Compliance: DPDP DPIA, ISO 27001, an India-region/on-prem deployment (Gnani Artha), and HIPAA mapping for expansion.
6. Pricing: per-completed-follow-up for individual clinics, and platform + volume tiers for chains.
