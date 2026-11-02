# Demo guide

## Before recording

1. `cd backend && uv run careloop seed`. This gives a fresh database with open alerts and six follow-ups due in the next few minutes.
2. Start the API (`uv run careloop serve`) and the dashboard (`pnpm dev`).
3. To demo voice, set `GNANI_API_KEY` and `LLM_API_KEY` in `backend/.env`. Check that `/api/health` shows `voice_enabled: true`.
4. Put the dashboard and the patient phone page side by side. The page is opened with the **Call now** or **Patient link** buttons.
5. Speak only scripted synthetic lines. No real names, numbers or medical history.

## 60-second cut

| Time | Shot |
|---|---|
| 0-8 s | Today board: open alerts, follow-up queue. "The clinic discharged 40 patients this week." |
| 8-25 s | **Call now** on Karthik Subramanian (Tamil derma) or Lakshmi Gowda (Kannada). Answer by voice and give consent. On the itching or fever question, say something like *"காயத்தில் சீழ் வருகிறது, காய்ச்சலும் இருக்கு"* ("there's pus from the wound and a fever too"). |
| 25-40 s | The urgent safety line plays in Tamil, and the dashboard toast and alert appear at the same moment. Open the report to show the evidence quote and the highlighted turn. |
| 40-52 s | Second call: Vikas Sharma (Hinglish, Prisma v3.0 code-mix). "Theek hoon, bas doctor se milna hai." The agent offers three slots and books one, and the schedule updates. |
| 52-60 s | Closing card: *10 Indian languages · Gnani Prisma + Timbre · live triage · DPDP-aware*. |

## Longer walkthrough beats

- **Consent declined:** the call ends politely and no health data is stored (consent log on the patient page).
- **No answer:** press Decline three times, or wait out the ring timeout. A retry follows, then a WhatsApp/SMS fallback appears under **Messages**.
- **Negation:** "No fever" is not flagged. "Bukhar nahi hai but seene mein dard hai" is an EMERGENCY.
- **Adherence:** Anil Nair has missed doses in two check-ins, so the pharmacy is flagged.
- **FHIR export** from any report, and the **Analytics** page.
- **Admin role** (sidebar switcher) can see the audit log through the API.

## Submission checklist

- [ ] Models named: Prisma v2.5 / v3.0 (STT), Timbre v2.5 (TTS), and the dialogue LLM
- [ ] Each teammate's contribution listed
- [ ] Only synthetic data in the repo, screenshots and video
- [ ] `eval/run_eval.py languages` and `noise` run, with the tables pasted into the README
- [ ] Public LinkedIn/X post with `#GnaniAI #GreatIndianAIInternshipChallenge`, tagging Gnani AI, and nominated in the form
- [ ] Submitted before Nov 10, 11:59 PM IST
