"""One follow-up call: state, tool handlers and live triage.

The same session backs voice calls (Pipecat) and text calls (browser chat, tests, offline
brain). Tool handlers take plain JSON arguments and return JSON-able dicts for the LLM.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlmodel import col, select

from careloop import booking, events
from careloop.config import settings
from careloop.db import session_scope
from careloop.languages import LANGUAGES, lang, line
from careloop.models import (
    IST,
    Answer,
    Call,
    CallStatus,
    Clinic,
    Consent,
    Doctor,
    Encounter,
    FollowupPlan,
    MedAdherence,
    Outbox,
    Patient,
    PlanStatus,
    TriageEvent,
    Urgency,
    to_ist,
    utcnow,
)
from careloop.packs import AnswerError, Pack, get_pack
from careloop.triage import Hit, evaluate_pack_rules, scan_utterance

# end_call reasons that may end the call before every question is answered.
EARLY_END_REASONS = {"consent_declined", "emergency", "patient_request", "callback", "patient_unavailable", "wrong_person"}


@dataclass
class TurnResult:
    """What the transport should do after a patient utterance is processed."""

    speak_now: list[str] = field(default_factory=list)  # verbatim lines to speak before the LLM replies
    llm_notes: list[str] = field(default_factory=list)  # system notes to add to the LLM context


class CallSession:
    def __init__(self, call_id: int):
        with session_scope() as db:
            call = db.get(Call, call_id)
            if call is None:
                raise ValueError(f"No call {call_id}")
            plan = db.get(FollowupPlan, call.plan_id)
            patient = db.get(Patient, call.patient_id)
            assert plan and patient
            encounter = db.get(Encounter, plan.encounter_id)
            assert encounter
            doctor = db.get(Doctor, encounter.doctor_id)
            clinic = db.get(Clinic, patient.clinic_id)
            assert doctor and clinic
        self.call, self.plan, self.patient = call, plan, patient
        self.encounter, self.doctor, self.clinic = encounter, doctor, clinic
        self.pack: Pack = get_pack(plan.pack_id)
        self.language = call.language or patient.language
        self.codemix = patient.codemix

        self.consent: bool | None = None
        self.answers: dict[str, Any] = {}
        self.answer_status: dict[str, str] = {}
        self.evidence: dict[str, str] = {}
        self.hits: list[Hit] = []
        self.level = Urgency.ROUTINE
        # Highest level whose safety line was already spoken; a line is only repeated if urgency rises.
        self._spoken_level = Urgency.ROUTINE
        self.unclear_streak = 0
        self.bookings: list[dict[str, Any]] = []
        self.medications: list[dict[str, Any]] = []
        self.department_suggestions: list[dict[str, str]] = []
        self.transcript: list[dict[str, Any]] = []
        self.latencies_ms: list[float] = []
        self.ended = False
        self.end_reason: str | None = None
        self.started_monotonic = time.monotonic()
        self.finalized = False

        # Hooks set by the transport.
        self.on_language_change: Callable[[str], None] | None = None

    # ---------------------------------------------------------------- lifecycle

    def start(self, mode: str) -> str:
        """Mark the call connected and return the opening (consent) line."""
        with session_scope() as db:
            call = db.get(Call, self.call.id)
            plan = db.get(FollowupPlan, self.plan.id)
            assert call and plan
            call.status = CallStatus.CONNECTED
            call.mode = mode
            call.started_at = utcnow()
            plan.status = PlanStatus.IN_PROGRESS
            db.add(call)
            db.add(plan)
            db.commit()
        events.publish("call", {"call_id": self.call.id, "patient_id": self.patient.id, "status": "connected", "mode": mode})
        opening = self.opening_line()
        self.add_assistant_text(opening)
        return opening

    def opening_line(self) -> str:
        first_name = self.patient.name.split()[0]
        return line(self.language, "consent", name=first_name, clinic=self.clinic.name, doctor=self.doctor.name)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_monotonic

    @property
    def unanswered(self) -> list[str]:
        return [k for k in self.pack.keys if k not in self.answer_status]

    # ---------------------------------------------------------------- utterances

    def add_assistant_text(self, text: str) -> None:
        if text.strip():
            self.transcript.append({"role": "assistant", "text": text.strip(), "t": round(self.elapsed_seconds, 1)})

    def on_user_text(self, text: str, language: str | None = None) -> TurnResult:
        """Record a final patient utterance and run layer-1 (lexicon) triage on it."""
        result = TurnResult()
        text = text.strip()
        if not text:
            return result
        turn = len(self.transcript)
        self.transcript.append({"role": "patient", "text": text, "t": round(self.elapsed_seconds, 1), "lang": language or self.language})
        for hit in scan_utterance(text):
            self._record_hit(hit, turn_index=turn)
            if hit.level >= Urgency.URGENT and hit.level > self._spoken_level:
                self._spoken_level = hit.level
                key = "emergency" if hit.level == Urgency.EMERGENCY else "urgent"
                safe_line = line(self.language, key)
                result.speak_now.append(safe_line)
                self.add_assistant_text(safe_line)
                next_step = (
                    "Confirm they will go to emergency care now, then call end_call with reason 'emergency'."
                    if hit.level == Urgency.EMERGENCY
                    else "Offer the earliest appointment (check_slots), then continue the remaining questions briefly."
                )
                result.llm_notes.append(
                    f"SAFETY: the patient's words \"{hit.evidence}\" matched red flag '{hit.reason}' "
                    f"({hit.level.name}). The care team has been alerted and this safety message was already spoken "
                    f"to the patient: \"{safe_line}\". Do not repeat it and do not diagnose. {next_step}"
                )
            elif hit.level == Urgency.REVIEW and not hit.negated:
                result.llm_notes.append(
                    f"Note: the patient mentioned '{hit.reason.lower()}'. Make sure the related question is answered."
                )
        return result

    def _record_hit(self, hit: Hit, turn_index: int | None = None) -> None:
        if any(h.rule_id == hit.rule_id and h.level >= hit.level for h in self.hits):
            return
        self.hits.append(hit)
        previous = self.level
        self.level = max(self.level, hit.level)
        with session_scope() as db:
            event = TriageEvent(
                call_id=self.call.id, patient_id=self.patient.id, level=int(hit.level), source=hit.source,
                rule_id=hit.rule_id, reason=hit.reason, evidence=hit.evidence, turn_index=turn_index,
            )
            db.add(event)
            if hit.level >= Urgency.URGENT:
                db.add(Outbox(
                    channel="nurse_alert", recipient=f"On-call nurse, {self.clinic.name}", patient_id=self.patient.id,
                    body=f"[{hit.level.name}] {self.patient.name} ({self.pack.name}): {hit.reason}. Patient said: \"{hit.evidence}\"",
                ))
            db.commit()
            db.refresh(event)
        logger.info(f"call {self.call.id}: triage {hit.level.name} {hit.rule_id} ({hit.source})")
        events.publish("alert", {
            "id": event.id, "call_id": self.call.id, "patient_id": self.patient.id, "patient_name": self.patient.name,
            "level": hit.level.name, "reason": hit.reason, "evidence": hit.evidence, "rule_id": hit.rule_id,
            "source": hit.source, "raised": hit.level > previous, "created_at": event.created_at,
        })

    # ---------------------------------------------------------------- tools

    def tool_record_consent(self, granted: bool) -> dict[str, Any]:
        self.consent = bool(granted)
        with session_scope() as db:
            db.add(Consent(patient_id=self.patient.id, call_id=self.call.id, language=self.language, granted=self.consent))
            call = db.get(Call, self.call.id)
            assert call
            call.consent_given = self.consent
            db.add(call)
            db.commit()
        if not self.consent:
            return {"ok": True, "next": "Call end_call with reason 'consent_declined'. Say nothing else."}
        first = self.pack.questions[0]
        return {"ok": True, "next": f"Ask the first question ({first.key}): {first.ask}"}

    def tool_record_answer(
        self, key: str, value: Any = None, status: str = "answered", confidence: float = 1.0, evidence_quote: str = ""
    ) -> dict[str, Any]:
        if not self.consent:
            return {"ok": False, "error": "Consent has not been recorded. Health answers cannot be stored yet."}
        try:
            question = self.pack.question(key)
            if status == "answered":
                value = question.normalise(value)
            elif status not in ("declined", "unclear"):
                return {"ok": False, "error": "status must be answered, declined or unclear"}
            else:
                value = None
        except AnswerError as e:
            return {"ok": False, "error": str(e)}

        self.unclear_streak = self.unclear_streak + 1 if status == "unclear" else 0
        self.answer_status[key] = status
        if status == "answered":
            self.answers[key] = value
        self.evidence[key] = evidence_quote
        with session_scope() as db:
            db.add(Answer(
                call_id=self.call.id, key=key, value=value, status=status, confidence=float(confidence),
                evidence_quote=evidence_quote, turn_index=len(self.transcript) - 1,
            ))
            db.commit()
        events.publish("answer", {"call_id": self.call.id, "key": key, "value": value, "status": status})

        result: dict[str, Any] = {"ok": True, "recorded": {key: value if status == "answered" else status}}
        # Layer 2: pack rules on every new answer.
        fired = []
        for hit in evaluate_pack_rules(self.pack, self.answers, self.evidence):
            if not any(h.rule_id == hit.rule_id for h in self.hits):
                self._record_hit(hit)
                fired.append(hit)
        if fired:
            top = fired[0]
            if top.level >= Urgency.URGENT and top.level > self._spoken_level:
                self._spoken_level = top.level
                result["say_exactly"] = line(self.language, "urgent")
                result["safety"] = (
                    f"Red flag '{top.reason}' ({top.level.name}). The care team has been alerted and the urgent "
                    "safety message is spoken to the patient automatically; do not repeat it. "
                    "Offer the earliest appointment with check_slots."
                )
            else:
                result["flagged_for_review"] = [h.reason for h in fired]
        if question.medication and value in ("some", "none"):
            result["follow_up"] = "Ask which medicine is being missed and why, then call record_medication for each."
        if self.unclear_streak >= 2:
            result["follow_up"] = (
                f"Two unclear answers in a row. Say: \"{line(self.language, 'callback')}\" "
                "then call end_call with reason 'callback'."
            )
        remaining = self.unanswered
        result["remaining_questions"] = [
            {"key": k, "ask": self.pack.question(k).ask} for k in remaining[:2]
        ]
        if not remaining:
            result["next"] = "All questions are covered. Handle booking if wanted, ask if there is anything else, then end_call('completed')."
        return result

    def tool_escalate(self, level: str, reason: str, evidence_quote: str = "") -> dict[str, Any]:
        try:
            lvl = Urgency.parse(level)
        except KeyError:
            return {"ok": False, "error": "level must be REVIEW, URGENT or EMERGENCY"}
        self._record_hit(Hit(lvl, "agent", f"agent_{lvl.name.lower()}", reason, evidence_quote), turn_index=len(self.transcript) - 1)
        if lvl >= Urgency.URGENT and lvl > self._spoken_level:
            self._spoken_level = lvl
            key = "emergency" if lvl == Urgency.EMERGENCY else "urgent"
            return {
                "ok": True,
                "say_exactly": line(self.language, key),
                "note": "This safety message is spoken to the patient automatically; do not repeat it.",
            }
        return {"ok": True, "note": "Flagged for doctor review."}

    def tool_check_slots(self, preferred_date: str | None = None, specialty: str | None = None) -> dict[str, Any]:
        after = utcnow()
        if preferred_date:
            try:
                # Interpret the date as IST midnight.
                day = datetime.fromisoformat(preferred_date).replace(tzinfo=IST)
                after = max(after, day.astimezone(timezone.utc))
            except ValueError:
                pass
        with session_scope() as db:
            if specialty and specialty != self.doctor.specialty:
                rows = booking.find_slots(db, clinic_id=self.clinic.id, specialty=specialty, after=after)
            else:
                rows = booking.find_slots(db, clinic_id=self.clinic.id, doctor_id=self.doctor.id, after=after)
                if not rows:
                    rows = booking.find_slots(db, clinic_id=self.clinic.id, specialty=self.doctor.specialty, after=after)
        if not rows:
            return {"ok": True, "slots": [], "note": "No free slots. Tell the patient the clinic will call to arrange a visit."}
        return {
            "ok": True,
            "slots": [{"slot_id": s.id, "when": booking.describe_slot(s, d), "doctor": d.name} for s, d in rows],
            "instruction": "Offer these in one short sentence. Read back the chosen one and get a yes before book_slot.",
        }

    def tool_book_slot(self, slot_id: int, reason: str = "follow-up") -> dict[str, Any]:
        with session_scope() as db:
            try:
                appt = booking.book(db, slot_id=int(slot_id), patient_id=self.patient.id, call_id=self.call.id, reason=reason)
            except booking.BookingError as e:
                return {"ok": False, "error": str(e)}
            from careloop.models import Slot

            slot = db.get(Slot, appt.slot_id)
            doc = db.get(Doctor, appt.doctor_id)
            assert slot and doc
            when = booking.describe_slot(slot, doc)
        self.bookings.append({"action": "booked", "appointment_id": appt.id, "when": when})
        events.publish("booking", {"call_id": self.call.id, "patient_id": self.patient.id, "action": "booked", "when": when})
        return {"ok": True, "appointment_id": appt.id, "confirmed": when}

    def tool_list_appointments(self) -> dict[str, Any]:
        with session_scope() as db:
            rows = booking.active_appointments(db, self.patient.id)
            return {"ok": True, "appointments": [
                {"appointment_id": a.id, "when": booking.describe_slot(s, d)} for a, s, d in rows
            ]}

    def tool_reschedule(self, appointment_id: int, new_slot_id: int) -> dict[str, Any]:
        with session_scope() as db:
            try:
                appt = booking.reschedule(
                    db, appointment_id=int(appointment_id), new_slot_id=int(new_slot_id),
                    patient_id=self.patient.id, call_id=self.call.id,
                )
            except booking.BookingError as e:
                return {"ok": False, "error": str(e)}
            from careloop.models import Slot

            slot = db.get(Slot, appt.slot_id)
            doc = db.get(Doctor, appt.doctor_id)
            assert slot and doc
            when = booking.describe_slot(slot, doc)
        self.bookings.append({"action": "rescheduled", "appointment_id": appt.id, "when": when})
        events.publish("booking", {"call_id": self.call.id, "patient_id": self.patient.id, "action": "rescheduled", "when": when})
        return {"ok": True, "appointment_id": appt.id, "confirmed": when}

    def tool_cancel_appointment(self, appointment_id: int) -> dict[str, Any]:
        with session_scope() as db:
            try:
                appt = booking.cancel(db, appointment_id=int(appointment_id), patient_id=self.patient.id)
            except booking.BookingError as e:
                return {"ok": False, "error": str(e)}
        self.bookings.append({"action": "cancelled", "appointment_id": appt.id})
        events.publish("booking", {"call_id": self.call.id, "patient_id": self.patient.id, "action": "cancelled"})
        return {"ok": True, "cancelled": appt.id}

    def tool_suggest_department(self, complaint: str) -> dict[str, Any]:
        dept = booking.suggest_department(complaint)
        self.department_suggestions.append({"complaint": complaint, "department": dept})
        if dept == "emergency":
            return self.tool_escalate("EMERGENCY", f"Complaint outside {self.doctor.specialty}: {complaint}", complaint)
        if dept != self.doctor.specialty:
            self._record_hit(
                Hit(Urgency.REVIEW, "routing", "route_other_department", f"Complaint for {dept}: {complaint}", complaint)
            )
            return {"ok": True, "department": dept, "instruction": f"Offer a {dept.replace('_', ' ')} appointment via check_slots(specialty='{dept}')."}
        return {"ok": True, "department": dept, "instruction": "Same department as the original visit."}

    def tool_record_medication(self, medication: str, taken: str, reason: str = "") -> dict[str, Any]:
        if not self.consent:
            return {"ok": False, "error": "Consent has not been recorded."}
        taken = taken.strip().lower()
        if taken not in ("all", "some", "none"):
            return {"ok": False, "error": "taken must be all, some or none"}
        self.medications.append({"medication": medication, "taken": taken, "reason": reason})
        with session_scope() as db:
            db.add(MedAdherence(patient_id=self.patient.id, call_id=self.call.id, medication=medication, taken=taken, reason=reason))
            db.commit()
        return {"ok": True}

    def tool_set_language(self, language: str) -> dict[str, Any]:
        if language not in LANGUAGES:
            return {"ok": False, "error": f"Unsupported language. Choose from {sorted(LANGUAGES)}"}
        self.language = language
        if self.on_language_change:
            self.on_language_change(language)
        return {"ok": True, "instruction": f"From now on speak only {lang(language).english_name} ({lang(language).native_name})."}

    def tool_end_call(self, reason: str = "completed") -> dict[str, Any]:
        if reason not in EARLY_END_REASONS and self.unanswered and self.elapsed_seconds < settings.max_call_seconds:
            return {
                "ok": False,
                "error": "Questions are still unanswered. Ask them, or record them as declined/unclear.",
                "remaining": self.unanswered,
            }
        self.ended = True
        self.end_reason = reason
        closing = line(self.language, "consent_declined" if reason == "consent_declined" else "closing")
        if reason in ("emergency", "callback"):
            closing = ""
        if closing:
            self.add_assistant_text(closing)
        return {"ok": True, "closing_line": closing, "instruction": "The call is ending. Say nothing else."}

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"ok": False, "error": f"Unknown tool {name}"}
        try:
            return handler(**args)
        except TypeError as e:
            return {"ok": False, "error": f"Bad arguments for {name}: {e}"}

    # ---------------------------------------------------------------- end of call

    def patient_context(self) -> dict[str, Any]:
        return {
            "patient_name": self.patient.name,
            "age": self.patient.age,
            "clinic": self.clinic.name,
            "doctor": self.doctor.name,
            "specialty": self.doctor.specialty,
            "procedure": self.encounter.procedure_type,
            "discharged": to_ist(self.encounter.discharged_at).strftime("%d %b %Y"),
            "medications": self.encounter.medications,
        }

    def finalize(self, review: Callable[["CallSession"], dict[str, Any] | None] | None = None):
        """Persist transcript, run the end-of-call review and build the report. Idempotent."""
        if self.finalized:
            return None
        self.finalized = True
        from careloop.reports import build_report

        with session_scope() as db:
            call = db.get(Call, self.call.id)
            assert call
            call.ended_at = utcnow()
            call.transcript = self.transcript
            call.latencies_ms = self.latencies_ms
            call.language = self.language
            if self.consent is False:
                call.status = CallStatus.CONSENT_DECLINED
            elif self.consent and not self.unanswered:
                call.status = CallStatus.COMPLETED
            else:
                call.status = CallStatus.PARTIAL
            db.add(call)
            db.commit()
            status = call.status

        if self.consent is False:
            with session_scope() as db:
                plan = db.get(FollowupPlan, self.plan.id)
                assert plan
                plan.status = PlanStatus.CLOSED
                db.add(plan)
                db.commit()
            events.publish("call", {"call_id": self.call.id, "patient_id": self.patient.id, "status": status})
            return None

        review_result = None
        if review and self.consent:
            try:
                review_result = review(self)
            except Exception as e:  # the report must still be produced
                logger.warning(f"LLM review failed for call {self.call.id}: {e}")
        if review_result:
            try:
                lvl = Urgency.parse(review_result.get("level", "ROUTINE"))
            except KeyError:
                lvl = Urgency.ROUTINE
            if lvl > self.level:  # raise-only
                self._record_hit(Hit(lvl, "llm_review", "llm_review", review_result.get("reason", "LLM review"), review_result.get("evidence", "")))

        self._record_adherence_rows()
        self._check_adherence_pattern()

        with session_scope() as db:
            report = build_report(db, self, status=status, summary=(review_result or {}).get("summary"))
            plan = db.get(FollowupPlan, self.plan.id)
            assert plan
            plan.status = PlanStatus.COMPLETED if status == CallStatus.COMPLETED else PlanStatus.CLOSED
            db.add(plan)
            db.commit()
        events.publish("report", {
            "report_id": report.id, "call_id": self.call.id, "patient_id": self.patient.id,
            "patient_name": self.patient.name, "urgency": Urgency(report.urgency).name, "status": report.status,
        })
        events.publish("call", {"call_id": self.call.id, "patient_id": self.patient.id, "status": status})
        return report

    def _record_adherence_rows(self) -> None:
        """If the agent only captured the summary adherence answer, record it per medicine."""
        overall = self.answers.get("med_adherence")
        if overall is None or self.medications:
            return
        with session_scope() as db:
            for med in self.encounter.medications or ["prescribed medicines"]:
                db.add(MedAdherence(patient_id=self.patient.id, call_id=self.call.id, medication=med, taken=overall,
                                    reason=self.evidence.get("med_adherence", "")))
                self.medications.append({"medication": med, "taken": overall, "reason": ""})
            db.commit()

    def _check_adherence_pattern(self) -> None:
        """Flag to doctor and pharmacy after N consecutive check-ins with missed doses."""
        n = settings.adherence_miss_threshold
        with session_scope() as db:
            rows = db.exec(
                select(MedAdherence).where(MedAdherence.patient_id == self.patient.id)
                .order_by(col(MedAdherence.recorded_at).desc())
            ).all()
        by_call: dict[int | None, bool] = {}
        for r in rows:
            missed = r.taken != "all"
            by_call[r.call_id] = by_call.get(r.call_id, False) or missed
        recent = list(by_call.values())[:n]
        if len(recent) >= n and all(recent):
            self._record_hit(Hit(Urgency.REVIEW, "adherence", "adherence_pattern",
                                 f"Missed medicines in {n} consecutive check-ins"))
            with session_scope() as db:
                db.add(Outbox(channel="pharmacy", recipient=f"Pharmacy, {self.clinic.name}", patient_id=self.patient.id,
                              body=f"{self.patient.name} has missed doses in {n} consecutive follow-ups. Please counsel."))
                db.commit()
