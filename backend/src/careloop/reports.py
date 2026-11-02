"""Per-call report, trend versus the previous check-in, and FHIR-shaped export."""

from typing import TYPE_CHECKING, Any

from sqlmodel import Session, col, select

from careloop.models import Report, TriageEvent, Urgency, utcnow
from careloop.packs import get_pack

if TYPE_CHECKING:
    from careloop.agent.session import CallSession


def template_summary(s: "CallSession") -> str:
    """Deterministic English summary, used when no LLM is configured."""
    parts = []
    for q in s.pack.questions:
        status = s.answer_status.get(q.key)
        if status == "answered":
            parts.append(f"{q.key.replace('_', ' ')}: {s.answers[q.key]}")
        elif status:
            parts.append(f"{q.key.replace('_', ' ')}: {status}")
    flags = sorted({h.reason for h in s.hits if h.level >= Urgency.REVIEW and not h.negated})
    text = f"{s.pack.name} for {s.patient.name}. " + ("; ".join(parts) + "." if parts else "No answers captured.")
    if flags:
        text += " Flags: " + "; ".join(flags) + "."
    if s.bookings:
        text += " Booking: " + "; ".join(f"{b['action']} {b.get('when', '')}".strip() for b in s.bookings) + "."
    return text


def _trend(db: Session, s: "CallSession", score: float | None) -> dict[str, Any] | None:
    prev = db.exec(
        select(Report).where(Report.patient_id == s.patient.id, Report.call_id != s.call.id)
        .order_by(col(Report.created_at).desc())
    ).first()
    if prev is None:
        return None
    prev_answers = {k: v.get("value") for k, v in (prev.structured.get("answers") or {}).items()}
    changes = {
        k: {"before": prev_answers[k], "now": v}
        for k, v in s.answers.items()
        if k in prev_answers and prev_answers[k] != v
    }
    return {
        "previous_report_id": prev.id,
        "previous_score": prev.recovery_score,
        "score_delta": round(score - prev.recovery_score, 1) if score is not None and prev.recovery_score is not None else None,
        "changes": changes,
    }


def build_report(db: Session, s: "CallSession", *, status: str, summary: str | None = None) -> Report:
    score = s.pack.recovery_score(s.answers)
    events = db.exec(select(TriageEvent).where(TriageEvent.call_id == s.call.id)).all()
    urgency = max([Urgency.ROUTINE, *(Urgency(e.level) for e in events)])
    structured = {
        "pack": {"id": s.pack.id, "name": s.pack.name},
        "context": s.patient_context(),
        "language": s.language,
        "consent": s.consent,
        "duration_seconds": round(s.elapsed_seconds),
        "answers": {
            q.key: {
                "value": s.answers.get(q.key),
                "status": s.answer_status.get(q.key, "missing"),
                "evidence": s.evidence.get(q.key, ""),
                "question": q.ask,
            }
            for q in s.pack.questions
        },
        "triage": [
            {"level": Urgency(e.level).name, "source": e.source, "rule_id": e.rule_id, "reason": e.reason,
             "evidence": e.evidence, "turn_index": e.turn_index}
            for e in sorted(events, key=lambda e: -e.level)
        ],
        "bookings": s.bookings,
        "medications": s.medications,
        "department_suggestions": s.department_suggestions,
        "trend": _trend(db, s, score),
        "end_reason": s.end_reason,
        "median_latency_ms": sorted(s.latencies_ms)[len(s.latencies_ms) // 2] if s.latencies_ms else None,
    }
    report = Report(
        call_id=s.call.id, patient_id=s.patient.id, pack_id=s.pack.id,
        status="complete" if status == "completed" else "partial",
        urgency=int(urgency), summary_en=summary or template_summary(s), structured=structured,
        recovery_score=score, created_at=utcnow(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


_LOINC_HINTS = {
    "pain_score": ("72514-3", "Pain severity - 0-10 verbal numeric rating"),
    "fasting_sugar": ("1558-6", "Fasting glucose [Mass/volume] in Serum or Plasma"),
}


def fhir_bundle(report: Report) -> dict[str, Any]:
    """A FHIR R4 collection Bundle: one QuestionnaireResponse plus an Observation per answer.

    Shaped for import into an HIS/EMR; codes are illustrative and need mapping per hospital.
    """
    pack = get_pack(report.pack_id)
    patient_ref = {"reference": f"Patient/{report.patient_id}"}
    answers = report.structured.get("answers", {})
    items = []
    observations = []
    for q in pack.questions:
        a = answers.get(q.key, {})
        value = a.get("value")
        item: dict[str, Any] = {"linkId": q.key, "text": q.ask}
        if value is not None:
            if isinstance(value, bool):
                item["answer"] = [{"valueBoolean": value}]
            elif isinstance(value, int | float):
                item["answer"] = [{"valueDecimal": value}]
            else:
                item["answer"] = [{"valueString": str(value)}]
            code = _LOINC_HINTS.get(q.key)
            obs: dict[str, Any] = {
                "resourceType": "Observation",
                "status": "final",
                "subject": patient_ref,
                "effectiveDateTime": report.created_at.isoformat(),
                "code": {
                    "coding": [{"system": "http://loinc.org", "code": code[0], "display": code[1]}] if code else [],
                    "text": q.key.replace("_", " "),
                },
                "note": [{"text": f"Patient said: {a.get('evidence', '')}"}] if a.get("evidence") else [],
            }
            if isinstance(value, bool):
                obs["valueBoolean"] = value
            elif isinstance(value, int | float):
                obs["valueQuantity"] = {"value": value, "unit": q.unit or ("score" if q.type == "scale" else "")}
            else:
                obs["valueString"] = str(value)
            observations.append(obs)
        items.append(item)
    qr = {
        "resourceType": "QuestionnaireResponse",
        "id": f"careloop-report-{report.id}",
        "status": "completed" if report.status == "complete" else "in-progress",
        "questionnaire": f"urn:careloop:pack:{pack.id}",
        "subject": patient_ref,
        "authored": report.created_at.isoformat(),
        "item": items,
        "extension": [{"url": "urn:careloop:urgency", "valueString": Urgency(report.urgency).name}],
    }
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": qr}, *({"resource": o} for o in observations)],
    }
