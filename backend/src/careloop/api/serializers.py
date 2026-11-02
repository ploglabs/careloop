from typing import Any

from careloop.languages import lang
from careloop.models import (
    Appointment,
    Call,
    Doctor,
    FollowupPlan,
    Patient,
    Report,
    Slot,
    TriageEvent,
    Urgency,
)


def patient_brief(p: Patient) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "age": p.age, "sex": p.sex, "language": p.language,
        "language_name": lang(p.language).english_name, "codemix": p.codemix, "phone": p.phone,
    }


def alert(e: TriageEvent, p: Patient | None = None) -> dict[str, Any]:
    return {
        "id": e.id, "call_id": e.call_id, "patient_id": e.patient_id, "patient_name": p.name if p else None,
        "level": Urgency(e.level).name, "source": e.source, "rule_id": e.rule_id, "reason": e.reason,
        "evidence": e.evidence, "turn_index": e.turn_index, "created_at": e.created_at,
        "acked_by": e.acked_by, "acked_at": e.acked_at, "assigned_to": e.assigned_to,
    }


def report(r: Report, p: Patient | None = None) -> dict[str, Any]:
    return {
        "id": r.id, "call_id": r.call_id, "patient_id": r.patient_id, "patient_name": p.name if p else None,
        "pack_id": r.pack_id, "pack_name": r.structured.get("pack", {}).get("name"), "status": r.status,
        "urgency": Urgency(r.urgency).name, "summary": r.summary_en, "recovery_score": r.recovery_score,
        "created_at": r.created_at, "structured": r.structured,
    }


def report_brief(r: Report, p: Patient | None = None) -> dict[str, Any]:
    d = report(r, p)
    d.pop("structured")
    return d


def call(c: Call) -> dict[str, Any]:
    return {
        "id": c.id, "plan_id": c.plan_id, "patient_id": c.patient_id, "mode": c.mode, "status": c.status,
        "language": c.language, "rang_at": c.rang_at, "started_at": c.started_at, "ended_at": c.ended_at,
        "consent_given": c.consent_given, "transcript": c.transcript, "latencies_ms": c.latencies_ms,
    }


def plan(pl: FollowupPlan, p: Patient | None = None) -> dict[str, Any]:
    return {
        "id": pl.id, "patient_id": pl.patient_id, "patient_name": p.name if p else None, "pack_id": pl.pack_id,
        "due_at": pl.due_at, "status": pl.status, "attempts": pl.attempts, "next_attempt_at": pl.next_attempt_at,
        "token": pl.token, "fallback_sent_at": pl.fallback_sent_at,
        "language": p.language if p else None,
    }


def appointment(a: Appointment, s: Slot, d: Doctor) -> dict[str, Any]:
    return {
        "id": a.id, "patient_id": a.patient_id, "doctor": d.name, "specialty": d.specialty, "start": s.start,
        "status": a.status, "source": a.source, "reason": a.reason, "call_id": a.call_id,
    }
