"""Slot search and booking.

A slot is claimed with a conditional UPDATE (`... WHERE status = 'free'`), so two calls racing
for the same slot cannot both win, on SQLite or Postgres.
"""

from datetime import datetime, timedelta

from sqlalchemy import update
from sqlmodel import Session, col, select

from careloop.models import Appointment, Doctor, Slot, to_ist, utcnow

# Where a complaint outside the original specialty should go.
DEPARTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "emergency": ("chest pain", "can't breathe", "unconscious", "fainted", "seizure", "heavy bleeding", "stroke"),
    "cardiology": ("palpitation", "heart", "bp", "blood pressure"),
    "general_surgery": ("wound", "stitches", "incision", "surgery"),
    "dermatology": ("rash", "itch", "skin", "acne", "pimple", "eczema", "redness"),
    "endocrinology": ("sugar", "diabetes", "thyroid", "insulin"),
    "orthopedics": ("knee", "joint", "back pain", "fracture", "bone"),
    "general_medicine": ("fever", "cough", "cold", "stomach", "vomiting", "headache"),
}


class BookingError(Exception):
    pass


def suggest_department(complaint: str) -> str:
    text = complaint.lower()
    for dept, words in DEPARTMENT_KEYWORDS.items():
        if any(w in text for w in words):
            return dept
    return "general_medicine"


def find_slots(
    db: Session,
    *,
    clinic_id: int,
    doctor_id: int | None = None,
    specialty: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int = 3,
) -> list[tuple[Slot, Doctor]]:
    after = after or utcnow()
    q = (
        select(Slot, Doctor)
        .join(Doctor, col(Doctor.id) == Slot.doctor_id)
        .where(Slot.status == "free", Slot.start >= after, Doctor.clinic_id == clinic_id)
        .order_by(col(Slot.start))
        .limit(limit)
    )
    if before is not None:
        q = q.where(Slot.start < before)
    if doctor_id is not None:
        q = q.where(Slot.doctor_id == doctor_id)
    if specialty:
        q = q.where(Doctor.specialty == specialty)
    return list(db.exec(q).all())


def _claim(db: Session, slot_id: int, patient_id: int) -> Slot:
    result = db.exec(  # type: ignore[call-overload]
        update(Slot)
        .where(col(Slot.id) == slot_id, col(Slot.status) == "free")
        .values(status="booked", patient_id=patient_id)
    )
    if result.rowcount != 1:
        db.rollback()
        raise BookingError("That slot was just taken. Please offer another one.")
    slot = db.get(Slot, slot_id)
    assert slot is not None
    db.refresh(slot)
    return slot


def book(db: Session, *, slot_id: int, patient_id: int, call_id: int | None, reason: str = "", source: str = "voice_agent") -> Appointment:
    if db.get(Slot, slot_id) is None:
        raise BookingError(f"No slot with id {slot_id}")
    slot = _claim(db, slot_id, patient_id)
    appt = Appointment(
        slot_id=slot_id, patient_id=patient_id, doctor_id=slot.doctor_id, call_id=call_id, reason=reason, source=source
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def _release(db: Session, appt: Appointment) -> None:
    db.exec(  # type: ignore[call-overload]
        update(Slot).where(col(Slot.id) == appt.slot_id).values(status="free", patient_id=None)
    )


def cancel(db: Session, *, appointment_id: int, patient_id: int) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if appt is None or appt.patient_id != patient_id or appt.status != "booked":
        raise BookingError("No active appointment with that id for this patient")
    _release(db, appt)
    appt.status = "cancelled"
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def reschedule(db: Session, *, appointment_id: int, new_slot_id: int, patient_id: int, call_id: int | None) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if appt is None or appt.patient_id != patient_id or appt.status != "booked":
        raise BookingError("No active appointment with that id for this patient")
    if db.get(Slot, new_slot_id) is None:
        raise BookingError(f"No slot with id {new_slot_id}")
    # Claim the new slot first so a failed claim leaves the old booking intact.
    slot = _claim(db, new_slot_id, patient_id)
    _release(db, appt)
    appt.status = "rescheduled"
    new = Appointment(
        slot_id=new_slot_id, patient_id=patient_id, doctor_id=slot.doctor_id, call_id=call_id,
        reason=appt.reason, source="voice_agent",
    )
    db.add(appt)
    db.add(new)
    db.commit()
    db.refresh(new)
    return new


def active_appointments(db: Session, patient_id: int) -> list[tuple[Appointment, Slot, Doctor]]:
    q = (
        select(Appointment, Slot, Doctor)
        .join(Slot, col(Slot.id) == Appointment.slot_id)
        .join(Doctor, col(Doctor.id) == Appointment.doctor_id)
        .where(Appointment.patient_id == patient_id, Appointment.status == "booked", Slot.start >= utcnow() - timedelta(hours=1))
        .order_by(col(Slot.start))
    )
    return list(db.exec(q).all())


def describe_slot(slot: Slot, doctor: Doctor) -> str:
    start = to_ist(slot.start)
    days_ahead = (start.date() - to_ist(utcnow()).date()).days
    relative = {0: "today, ", 1: "tomorrow, ", 2: "day after tomorrow, "}.get(days_ahead, "")
    return f"{relative}{start:%A %d %B, %I:%M %p} with {doctor.name}"
