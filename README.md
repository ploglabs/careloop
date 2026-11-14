<p align="center">
  <img src="web/src/app/icon.png" alt="CareLoop logo" width="96" height="96">
</p>

<h1 align="center">CareLoop</h1>

<p align="center">
  <strong>Multilingual post-discharge follow-up calls for Indian clinics and hospitals.</strong><br>
  Built on Gnani Prisma (speech-to-text) and Gnani Timbre (text-to-speech).
</p>

<p align="center">
  <a href="#what-it-does">What it does</a> ·
  <a href="#languages">Languages</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#running-it-locally">Run it locally</a> ·
  <a href="#privacy-and-compliance-dpdp-act-2023">Privacy</a> ·
  <a href="#built-vs-roadmap">Built vs roadmap</a>
</p>

<p align="center">
  <img alt="10 Indian languages" src="https://img.shields.io/badge/languages-10_Indian-0a0a0a">
  <img alt="Gnani Prisma and Timbre" src="https://img.shields.io/badge/speech-Gnani_Prisma_%2B_Timbre-0a0a0a">
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-0a0a0a">
  <img alt="Next.js 16" src="https://img.shields.io/badge/next.js-16-0a0a0a">
  <img alt="Synthetic data only" src="https://img.shields.io/badge/data-synthetic_only-0a0a0a">
</p>

A post-discharge care layer for clinics and hospital chains. A multilingual voice agent calls patients after they leave, runs a condition-specific check-in, triages what it hears in real time, books follow-up visits during the call, and hands the care team a structured report.

Built for the Gnani AI Great Indian AI Internship Challenge. One-page solution pitch: [PITCH.md](PITCH.md).

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
| `web/` | Clinic dashboard (charts drawn with [Dither Kit](https://tripwire.sh/dither-kit)) and patient call page |

## Running it locally

Everything below runs on your own machine against synthetic data. Text calls work with no API keys at all; voice calls need a Gnani key and an LLM key.

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | managed for you by uv |
| [uv](https://docs.astral.sh/uv/) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| pnpm | 11 (pinned in `web/package.json`) | `corepack enable pnpm` |
| Browser | Chrome or Edge recommended | needed for microphone access on voice calls |

### 1. Clone

```bash
git clone https://github.com/ploglabs/careloop.git
cd careloop
```

### 2. Start the backend (API, call agent, scheduler)

```bash
cd backend
cp .env.example .env
uv sync
uv run careloop seed      # resets careloop.db with synthetic clinics, patients, slots and past check-ins
uv run careloop serve     # API on http://localhost:8000
```

`careloop seed` takes a few seconds: it runs real scripted check-ins through the agent so the dashboard starts with reports and alerts. Re-run it any time to reset the database.

**API keys** go in `backend/.env`. What you get depends on which ones you set:

| Keys set | Text calls | Voice calls | End-of-call LLM summary | Languages |
|---|---|---|---|---|
| None | ✅ offline keyword agent | ❌ (Answer button is disabled) | ❌ | English only |
| `LLM_API_KEY` | ✅ LLM agent | ❌ | ✅ | all 10 |
| `LLM_API_KEY` + `GNANI_API_KEY` | ✅ | ✅ Prisma STT + Timbre TTS | ✅ | all 10 |

- `GNANI_API_KEY`: from [app.gnani.ai/voice](https://app.gnani.ai/voice).
- `LLM_API_KEY`: any OpenAI-compatible endpoint with tool calling. DeepInfra is the default ([get a key](https://deepinfra.com/dash/api_keys)); to use another provider, change `LLM_BASE_URL` and `LLM_MODEL` too.

Restart `careloop serve` after editing `.env`.

**Agent voice gender.** `CARELOOP_AGENT_VOICE` picks the Timbre voice: `female` (default), `male`, or `match` (same gender as the patient's record). Tamil and Telugu have no male Timbre v2.5 voice, so they stay female. The agent's own wording follows the voice it actually speaks with (Hindi "मैं समझ गई" vs "समझ गया", Punjabi "ਸਮਝ ਗਈ" vs "ਸਮਝ ਗਿਆ"), and it addresses the patient with forms that match their recorded gender.

**Dates.** The agent gets today's date and a 14-day calendar. When a patient asks for "tomorrow", "day after tomorrow", "next Friday", "in 3 days", "5 November", or *kal* / *parso* in any of the 10 languages, `check_slots` works out the date itself (`careloop/dates.py`) and returns slots on that day, or the nearest ones if that day is full.

### 3. Start the dashboard

In a second terminal:

```bash
cd web
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
pnpm install
pnpm dev                      # http://localhost:3000
```

Open [http://localhost:3000](http://localhost:3000). You should see the **Today** board with a follow-up queue on the right and an alert queue in the middle. A green **Live** dot in the top bar means the dashboard is receiving real-time events from the API.

### 4. Walk through it

**A text check-in (no keys needed)**
1. In the **Follow-up queue**, press **Call now** on any patient. Their phone page opens in a new tab and shows an incoming call.
2. Press **Text**. The agent asks for consent, then runs the check-in for that patient's condition.
3. Without an LLM key, reply in short English answers. For a dermatology patient, for example: `yes`, `better`, `2`, `no`, `no`, `no`, `all`, `no`, `no`.
4. When the call ends, go back to the dashboard: the report appears under **Latest reports**, and the patient's page shows the transcript, answers and score.

**A voice check-in (both keys)**
1. Press **Call now**, pick a language on the phone page, then press **Answer** and allow the microphone.
2. Speak naturally in that language. Use headphones so the agent doesn't hear itself through your speakers.
3. The status line shows **Speaking**, **Listening** or **Your turn**, and the transcript fills in as you talk. The agent hangs up by itself when the check-in is done.

**See triage escalate in real time**
- During a call, say something like `I have chest pain and I can't breathe properly` (post-surgery patient), or answer yes to both swelling and fever (dermatology patient).
- The agent speaks a scripted safety line straight away, and an alert toast pops up on the dashboard with a beep. The alert sits at the top of the **Alert queue** with the patient's own words and the rule that fired. **Acknowledge** or **Assign** it from there.

**Book a follow-up visit**
- When asked if you'd like to see the doctor, say yes and pick one of the offered slots. The booking shows under **Schedule** when you pick that patient's doctor.

**Other things to try**
- **Signed in as** (bottom of the sidebar) switches between nurse, doctor and admin views.
- **Patient link** on a queue item opens the same phone page a patient would get by WhatsApp or SMS after missed calls. The messages themselves land in **Messages**, since nothing is ever actually sent.
- If you leave a queue item alone, the scheduler rings it automatically when it's due, retries after a missed call, and falls back to the link.

### 5. Add more test data

These keep everything that's already in the database:

```bash
cd backend
uv run careloop queue --count 8 --spacing 3   # follow-ups due soon, 3 minutes apart
uv run careloop alerts --count 6              # patients whose check-ins raised red flags (real alerts and reports)
```

### 6. Run the automated tests

```bash
cd backend
uv run pytest                                    # 80 tests: triage cases, call flows, booking races, API
uv run careloop simulate 3 yes 2 better no ...   # one scripted call for plan 3, printed to the terminal
uv run careloop simulate 3 yes ... --llm         # the same with the LLM agent (needs LLM_API_KEY)

# Speech evaluation (needs GNANI_API_KEY, makes real API calls)
uv run python eval/run_eval.py languages         # per-language Timbre → Prisma round trip
uv run python eval/run_eval.py noise             # triage at 16 kHz, 8 kHz phone, 8 kHz + noise (SNR 10/5 dB)
```

```bash
cd web
pnpm lint
pnpm exec tsc --noEmit
```

The labelled triage cases live in `backend/eval/triage_cases.yaml`; add a case there and `pytest` checks it.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard says "Couldn't reach the CareLoop API" | Start the backend with `uv run careloop serve`, and check `NEXT_PUBLIC_API_URL` in `web/.env.local`. |
| **Answer** is greyed out on the phone page | Voice needs both `GNANI_API_KEY` and `LLM_API_KEY` in `backend/.env`. Restart the backend after adding them. |
| "This follow-up is already done" | That plan is finished. Use **Call now** on another patient, or add more with `careloop queue`. |
| No sound, or the microphone isn't picked up | Allow microphone access for `localhost:3000` in the browser's site settings, and check the right input device is selected. |
| The agent interrupts itself or hears its own voice | Use headphones. |
| Browser errors mention a CORS policy | Set `CORS_ORIGINS` in `backend/.env` to the dashboard's origin (default `http://localhost:3000`). |
| Port 8000 or 3000 is already in use | `uv run careloop serve --port 8001` (then update `NEXT_PUBLIC_API_URL`), or `pnpm dev --port 3001` (then update `PUBLIC_WEB_URL` and `CORS_ORIGINS`). |
| Dashboard doesn't pick up code changes | Stop `pnpm dev`, delete `web/.next`, and start it again. |
| You want a clean slate | `uv run careloop seed` resets the database. |

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
