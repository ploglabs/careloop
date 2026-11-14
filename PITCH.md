# CareLoop: Solution Pitch

**Multilingual AI follow-up calls that catch post-discharge complications early, for Indian clinics and hospitals.**
Built on Gnani Prisma (speech-to-text) and Gnani Timbre (text-to-speech). Repo: https://github.com/ploglabs/careloop

## The problem

Once a patient leaves the hospital, the care team loses sight of them. Infections, uncontrolled pain, missed medicines and warning signs go unnoticed until they turn into a readmission or an emergency visit. Nurses cannot phone every discharged patient, and many patients are more comfortable speaking Hindi, Tamil, Bengali or a mix like Hinglish than English. Missed follow-ups cost hospitals revenue too.

## The solution

CareLoop is a voice agent that calls each patient at the right time after discharge (day 1 and 7 after surgery, day 7 for dermatology, day 30 for chronic care) and talks to them in their own language.

1. **Structured check-in.** Questions come from condition packs (e.g. redness, itching 0-10, swelling, fever, adherence), so the clinic gets typed data, not a vague transcript. Every call opens with a spoken consent disclosure.
2. **Safety-first triage.** Three layers, each able only to *raise* urgency: a red-flag lexicon with negation handling in 10 languages, deterministic pack rules (`pain_score >= 8 → URGENT`), and an end-of-call LLM review. On an urgent finding, a fixed safety line is spoken verbatim and a nurse alert appears live on the dashboard with the patient's own words.
3. **Action in the call.** Books, reschedules or cancels follow-up visits against real slots, routes to another department when needed, and flags repeated missed medicines to the doctor and pharmacy. If nobody answers, it retries and falls back to a WhatsApp/SMS link.
4. **Clinic dashboard.** Live alert queue, flagged-patient view, per-call reports with trends, analytics, and FHIR R4 / CSV export for HIS/EMR systems.

## Why it works

- **10 Indian languages plus code-mixed speech** via Prisma v2.5/v3.0 and Timbre v2.5, with measured speech round-trip quality per language.
- **Safe by design:** no LLM improvisation on emergencies; every alert is explainable (rule fired + evidence quote).
- **DPDP Act 2023 aligned:** recorded consent, no raw audio stored, role-based access with audit log, and erasure on request.
- **Fits existing systems:** standard FHIR output, configurable YAML packs per specialty.

## Impact

Earlier detection of complications, fewer avoidable readmissions, more completed follow-up visits, and nurses who spend time on the patients who need them instead of on routine calls.

## Status and next steps

**Built:** voice and text calls, 3-layer triage, in-call booking, adherence tracking, dashboard, reports, FHIR/CSV export, consent and audit, evaluation harness. All demo data is synthetic.
**Next:** real phone lines (Exotel/Ozonetel) and WhatsApp Business, live HIS/EMR and ABDM integration, a validated readmission-risk model, and clinician-authored packs for more specialties.
