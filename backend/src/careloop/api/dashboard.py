from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select
from sse_starlette.sse import EventSourceResponse

from careloop import analytics, events
from careloop.api import serializers as ser
from careloop.api.deps import STAFF_ROLES, User, audit, current_user
from careloop.config import settings
from careloop.db import get_session
from careloop.languages import LANGUAGES
from careloop.models import (
    IST,
    AuditLog,
    Call,
    CallStatus,
    Clinic,
    Doctor,
    Encounter,
    FollowupPlan,
    Outbox,
    Patient,
    PlanStatus,
    Report,
    Slot,
    TriageEvent,
    Urgency,
    utcnow,
)
from careloop.packs import all_packs

router = APIRouter(prefix="/api")


def _today_start_utc() -> datetime:
    today = datetime.now(IST).date()
    return datetime.combine(today, time.min, tzinfo=IST).astimezone(timezone.utc)


@router.get("/meta")
def meta(db: Session = Depends(get_session)):
    return {
        "voice_enabled": settings.voice_enabled,
        "llm_enabled": settings.llm_enabled,
        "languages": [{"code": l.code, "name": l.english_name, "native": l.native_name, "voice": l.voice} for l in LANGUAGES.values()],
        "packs": [{"id": p.id, "name": p.name, "specialty": p.specialty, "procedure_types": p.procedure_types,
                   "offset_days": p.offset_days, "questions": len(p.questions), "red_flags": len(p.red_flags)}
                  for p in all_packs().values()],
        "clinics": [c.model_dump() for c in db.exec(select(Clinic)).all()],
        "doctors": [d.model_dump() for d in db.exec(select(Doctor)).all()],
    }


@router.get("/today")
def today(db: Session = Depends(get_session), user: User = Depends(current_user)):
    start = _today_start_utc()
    calls = db.exec(select(Call).where(Call.rang_at >= start)).all()
    patients = {p.id: p for p in db.exec(select(Patient)).all()}
    open_alerts = db.exec(
        select(TriageEvent).where(col(TriageEvent.acked_at).is_(None), TriageEvent.level >= Urgency.REVIEW)
        .order_by(col(TriageEvent.level).desc(), col(TriageEvent.created_at).desc())
    ).all()
    plans = db.exec(
        select(FollowupPlan).where(col(FollowupPlan.status).in_([
            PlanStatus.SCHEDULED, PlanStatus.RINGING, PlanStatus.IN_PROGRESS, PlanStatus.RETRY, PlanStatus.FALLBACK,
        ])).order_by(col(FollowupPlan.due_at))
    ).all()
    reports = db.exec(select(Report).order_by(col(Report.created_at).desc()).limit(12)).all()
    week_ago = utcnow() - timedelta(days=7)
    flagged_week = {
        e.patient_id for e in db.exec(select(TriageEvent).where(TriageEvent.created_at >= week_ago, TriageEvent.level >= Urgency.REVIEW)).all()
    }
    return {
        "counts": {
            "calls_today": len(calls),
            "completed_today": sum(c.status in (CallStatus.COMPLETED, CallStatus.PARTIAL) for c in calls),
            "no_answer_today": sum(c.status == CallStatus.NO_ANSWER for c in calls),
            "open_alerts": len(open_alerts),
            "open_urgent": sum(e.level >= Urgency.URGENT for e in open_alerts),
            "flagged_patients_week": len(flagged_week),
            "pending_followups": len(plans),
        },
        "alerts": [ser.alert(e, patients.get(e.patient_id)) for e in open_alerts],
        "plans": [ser.plan(p, patients.get(p.patient_id)) for p in plans],
        "recent_reports": [ser.report_brief(r, patients.get(r.patient_id)) for r in reports],
    }


@router.get("/alerts")
def alerts(status: str = "open", db: Session = Depends(get_session), user: User = Depends(current_user)):
    q = select(TriageEvent).order_by(col(TriageEvent.created_at).desc())
    if status == "open":
        q = q.where(col(TriageEvent.acked_at).is_(None))
    patients = {p.id: p for p in db.exec(select(Patient)).all()}
    return [ser.alert(e, patients.get(e.patient_id)) for e in db.exec(q.limit(200)).all()]


class AssignBody(BaseModel):
    to: str


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    e = db.get(TriageEvent, alert_id)
    if e is None:
        raise HTTPException(404)
    e.acked_by, e.acked_at = user.name, utcnow()
    db.add(e)
    db.commit()
    audit(db, user, "ack_alert", "triage_event", alert_id)
    events.publish("alert_ack", {"id": alert_id, "acked_by": user.name})
    return ser.alert(e)


@router.post("/alerts/{alert_id}/assign")
def assign_alert(alert_id: int, body: AssignBody, db: Session = Depends(get_session), user: User = Depends(current_user)):
    e = db.get(TriageEvent, alert_id)
    if e is None:
        raise HTTPException(404)
    e.assigned_to = body.to
    db.add(e)
    db.commit()
    audit(db, user, f"assign_alert:{body.to}", "triage_event", alert_id)
    events.publish("alert_assign", {"id": alert_id, "assigned_to": body.to})
    return ser.alert(e)


@router.get("/flagged")
def flagged(
    days: int = 7, specialty: str | None = None, doctor_id: int | None = None, level: str | None = None,
    language: str | None = None, db: Session = Depends(get_session), user: User = Depends(current_user),
):
    since = utcnow() - timedelta(days=days)
    min_level = Urgency.parse(level) if level else Urgency.REVIEW
    rows = db.exec(
        select(Report, Patient, Encounter, Doctor, FollowupPlan, Call)
        .join(Patient, col(Patient.id) == Report.patient_id)
        .join(Call, col(Call.id) == Report.call_id)
        .join(FollowupPlan, col(FollowupPlan.id) == Call.plan_id)
        .join(Encounter, col(Encounter.id) == FollowupPlan.encounter_id)
        .join(Doctor, col(Doctor.id) == Encounter.doctor_id)
        .where(Report.created_at >= since, Report.urgency >= min_level)
        .order_by(col(Report.urgency).desc(), col(Report.created_at).desc())
    ).all()
    out, seen = [], set()
    for r, p, enc, doc, _plan, c in rows:
        if p.id in seen:
            continue
        if specialty and doc.specialty != specialty:
            continue
        if doctor_id and doc.id != doctor_id:
            continue
        if language and c.language != language:
            continue
        seen.add(p.id)
        out.append({
            "patient": ser.patient_brief(p), "report": ser.report_brief(r, p), "doctor": doc.name,
            "specialty": doc.specialty, "procedure": enc.procedure_type,
            "reasons": [t["reason"] for t in r.structured.get("triage", []) if t["level"] != "ROUTINE"][:4],
            "risk": analytics.readmission_risk(db, p),
        })
    return {"days": days, "count": len(out), "patients": out}


@router.get("/analytics")
def analytics_view(days: int = 30, db: Session = Depends(get_session), user: User = Depends(current_user)):
    return analytics.overview(db, days)


@router.get("/outbox")
def outbox(db: Session = Depends(get_session), user: User = Depends(current_user)):
    rows = db.exec(select(Outbox).order_by(col(Outbox.created_at).desc()).limit(100)).all()
    return [r.model_dump() for r in rows]


@router.get("/audit")
def audit_log(db: Session = Depends(get_session), user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Audit log is admin-only")
    return [r.model_dump() for r in db.exec(select(AuditLog).order_by(col(AuditLog.at).desc()).limit(200)).all()]


@router.get("/schedule")
def schedule(days: int = 7, doctor_id: int | None = None, db: Session = Depends(get_session), user: User = Depends(current_user)):
    end = utcnow() + timedelta(days=days)
    q = select(Slot, Doctor).join(Doctor, col(Doctor.id) == Slot.doctor_id).where(Slot.start >= utcnow(), Slot.start <= end)
    if doctor_id:
        q = q.where(Slot.doctor_id == doctor_id)
    patients = {p.id: p for p in db.exec(select(Patient)).all()}
    return [
        {"slot_id": s.id, "doctor": d.name, "doctor_id": d.id, "specialty": d.specialty, "start": s.start,
         "status": s.status, "patient_name": patients[s.patient_id].name if s.patient_id in patients else None}
        for s, d in db.exec(q.order_by(col(Slot.start))).all()
    ]


@router.get("/events")
async def stream(role: str = ""):
    # EventSource cannot send headers, so the demo role comes as a query parameter.
    if role not in STAFF_ROLES:
        raise HTTPException(403, "Live events are restricted to care-team roles")

    async def gen():
        yield {"event": "hello", "data": "{}"}
        async for event, data in events.subscribe():
            yield {"event": event, "data": data}

    return EventSourceResponse(gen(), ping=15)
