import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, col, select

from careloop import analytics
from careloop.api import serializers as ser
from careloop.api.deps import User, audit, current_user
from careloop.db import get_session
from careloop.languages import LANGUAGES
from careloop.models import (
    Answer,
    Appointment,
    Call,
    Consent,
    Doctor,
    Encounter,
    FollowupPlan,
    MedAdherence,
    Patient,
    PlanStatus,
    Report,
    Slot,
    Urgency,
    as_utc,
    utcnow,
)
from careloop.reports import fhir_bundle
from careloop.scheduler import create_plans_for_encounter

router = APIRouter(prefix="/api")


@router.get("/patients")
def list_patients(db: Session = Depends(get_session), user: User = Depends(current_user)):
    out = []
    for p in db.exec(select(Patient).order_by(Patient.name)).all():
        latest = db.exec(select(Report).where(Report.patient_id == p.id).order_by(col(Report.created_at).desc())).first()
        next_plan = db.exec(
            select(FollowupPlan).where(FollowupPlan.patient_id == p.id,
                                       col(FollowupPlan.status).not_in([PlanStatus.COMPLETED, PlanStatus.CLOSED]))
            .order_by(col(FollowupPlan.due_at))
        ).first()
        out.append({
            **ser.patient_brief(p),
            "latest_report": ser.report_brief(latest) if latest else None,
            "next_plan": ser.plan(next_plan) if next_plan else None,
            "risk": analytics.readmission_risk(db, p),
        })
    return out


@router.get("/patients/{patient_id}")
def patient_detail(patient_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404)
    audit(db, user, "view_patient", "patient", patient_id)
    encounters = db.exec(select(Encounter).where(Encounter.patient_id == p.id)).all()
    doctors = {d.id: d for d in db.exec(select(Doctor)).all()}
    appts = db.exec(
        select(Appointment, Slot, Doctor)
        .join(Slot, col(Slot.id) == Appointment.slot_id)
        .join(Doctor, col(Doctor.id) == Appointment.doctor_id)
        .where(Appointment.patient_id == p.id)
        .order_by(col(Slot.start).desc())
    ).all()
    return {
        "patient": ser.patient_brief(p),
        "risk": analytics.readmission_risk(db, p),
        "encounters": [{**e.model_dump(), "doctor": doctors[e.doctor_id].name} for e in encounters],
        "plans": [ser.plan(pl, p) for pl in db.exec(select(FollowupPlan).where(FollowupPlan.patient_id == p.id).order_by(FollowupPlan.due_at)).all()],
        "reports": [ser.report_brief(r, p) for r in db.exec(select(Report).where(Report.patient_id == p.id).order_by(col(Report.created_at).desc())).all()],
        "calls": [ser.call(c) for c in db.exec(select(Call).where(Call.patient_id == p.id).order_by(col(Call.rang_at).desc())).all()],
        "appointments": [ser.appointment(a, s, d) for a, s, d in appts],
        "adherence": [m.model_dump() for m in db.exec(select(MedAdherence).where(MedAdherence.patient_id == p.id).order_by(col(MedAdherence.recorded_at).desc())).all()],
        "consents": [c.model_dump() for c in db.exec(select(Consent).where(Consent.patient_id == p.id).order_by(col(Consent.created_at).desc())).all()],
    }


@router.get("/reports/{report_id}")
def report_detail(report_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404)
    p = db.get(Patient, r.patient_id)
    c = db.get(Call, r.call_id)
    audit(db, user, "view_report", "report", report_id)
    previous = db.exec(
        select(Report).where(Report.patient_id == r.patient_id, Report.created_at < r.created_at)
        .order_by(col(Report.created_at).desc())
    ).first()
    return {
        "report": ser.report(r, p),
        "patient": ser.patient_brief(p) if p else None,
        "call": ser.call(c) if c else None,
        "previous_report": ser.report(previous) if previous else None,
    }


@router.get("/reports/{report_id}/fhir")
def report_fhir(report_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404)
    audit(db, user, "export_fhir", "report", report_id)
    return fhir_bundle(r)


@router.get("/reports.csv")
def reports_csv(db: Session = Depends(get_session), user: User = Depends(current_user)):
    audit(db, user, "export_csv", "report", None)
    patients = {p.id: p for p in db.exec(select(Patient)).all()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["report_id", "created_at", "patient", "pack", "status", "urgency", "recovery_score", "summary"])
    for r in db.exec(select(Report).order_by(col(Report.created_at).desc())).all():
        w.writerow([r.id, r.created_at.isoformat(), patients[r.patient_id].name, r.pack_id, r.status,
                    Urgency(r.urgency).name, r.recovery_score, r.summary_en])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=careloop-reports.csv"})


class NewEncounter(BaseModel):
    patient_id: int | None = None
    # New patient fields (synthetic data only)
    name: str | None = None
    language: str = "en-IN"
    codemix: bool = False
    age: int | None = None
    doctor_id: int
    procedure_type: str
    discharged_at: datetime | None = None
    medications: list[str] = []


@router.post("/encounters")
def create_encounter(body: NewEncounter, db: Session = Depends(get_session), user: User = Depends(current_user)):
    """Record a discharge and schedule its follow-up calls from the matching condition pack."""
    doctor = db.get(Doctor, body.doctor_id)
    if doctor is None:
        raise HTTPException(400, "Unknown doctor")
    if body.language not in LANGUAGES:
        raise HTTPException(400, "Unsupported language")
    if body.patient_id:
        patient = db.get(Patient, body.patient_id)
        if patient is None:
            raise HTTPException(404, "Unknown patient")
    else:
        if not body.name:
            raise HTTPException(400, "name is required for a new patient")
        count = len(db.exec(select(Patient)).all())
        patient = Patient(clinic_id=doctor.clinic_id, name=body.name, phone=f"SYN-{2000 + count}",
                          language=body.language, codemix=body.codemix, age=body.age)
        db.add(patient)
        db.commit()
        db.refresh(patient)
    enc = Encounter(patient_id=patient.id, doctor_id=doctor.id, specialty=doctor.specialty,
                    procedure_type=body.procedure_type, discharged_at=as_utc(body.discharged_at or utcnow()),
                    medications=body.medications)
    db.add(enc)
    db.commit()
    db.refresh(enc)
    plans = create_plans_for_encounter(db, enc)
    if not plans:
        raise HTTPException(400, f"No condition pack covers procedure {body.procedure_type!r}")
    audit(db, user, "create_encounter", "encounter", enc.id)
    return {"patient": ser.patient_brief(patient), "encounter_id": enc.id, "plans": [ser.plan(pl, patient) for pl in plans]}


@router.post("/patients/{patient_id}/consent/withdraw")
def withdraw_consent(patient_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    """DPDP: the patient withdraws consent. Pending follow-ups are closed and no further calls are made."""
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404)
    for c in db.exec(select(Consent).where(Consent.patient_id == patient_id, col(Consent.withdrawn_at).is_(None))).all():
        c.withdrawn_at = utcnow()
        db.add(c)
    for pl in db.exec(select(FollowupPlan).where(FollowupPlan.patient_id == patient_id,
                                                 col(FollowupPlan.status).not_in([PlanStatus.COMPLETED, PlanStatus.CLOSED]))).all():
        pl.status = PlanStatus.CLOSED
        db.add(pl)
    db.commit()
    audit(db, user, "withdraw_consent", "patient", patient_id)
    return {"ok": True}


@router.post("/patients/{patient_id}/erase")
def erase_patient(patient_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    """DPDP right to erasure: strip transcripts, quotes and identity, keep de-identified aggregates."""
    if user.role != "admin":
        raise HTTPException(403, "Erasure is admin-only")
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404)
    calls = db.exec(select(Call).where(Call.patient_id == patient_id)).all()
    for c in calls:
        c.transcript = []
        db.add(c)
        for a in db.exec(select(Answer).where(Answer.call_id == c.id)).all():
            a.evidence_quote = ""
            db.add(a)
    for r in db.exec(select(Report).where(Report.patient_id == patient_id)).all():
        r.summary_en = "[erased]"
        r.structured = {"pack": r.structured.get("pack"), "erased": True}
        db.add(r)
    p.name, p.phone, p.age = f"Erased patient #{p.id}", "ERASED", None
    db.add(p)
    db.commit()
    audit(db, user, "erase_patient", "patient", patient_id)
    return {"ok": True}
