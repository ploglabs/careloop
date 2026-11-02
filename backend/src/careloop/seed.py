"""Synthetic demo data. Every name, number and record here is invented.

Builds two fictional providers (a single clinic and a hospital chain branch), doctors, patients
across all 10 languages, open slots, plans due now for live demo calls, and a history of
past check-ins produced by running scripted calls through the real agent.
"""

import asyncio
import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from careloop.agent.simulate import run_scripted_call
from careloop.db import reset_db, session_scope
from careloop.models import (
    IST,
    Answer,
    Call,
    Clinic,
    Doctor,
    Encounter,
    FollowupPlan,
    Report,
    Slot,
    MedAdherence,
    TriageEvent,
    utcnow,
)
from careloop.packs import get_pack

random.seed(7)

MEDS = {
    "derma_week1": ["Adapalene 0.1% gel", "Clindamycin lotion", "Cetirizine 10 mg"],
    "post_surgery": ["Paracetamol 650 mg", "Cefuroxime 500 mg", "Pantoprazole 40 mg"],
    "chronic_diabetes": ["Metformin 500 mg", "Glimepiride 1 mg"],
}

# (name, language, codemix, age, sex, doctor key, procedure, pack, history scripts)
PATIENTS = [
    ("Meera Kulkarni", "mr-IN", False, 34, "F", "derma", "acne_treatment", "derma_week1", ["derma_good"]),
    ("Arjun Shetty", "kn-IN", False, 29, "M", "derma", "eczema_treatment", "derma_week1", ["derma_infected"]),
    ("Priya Venkatesan", "ta-IN", False, 41, "F", "surgeon", "appendectomy", "post_surgery", ["surg_good"]),
    ("Rahul Verma", "hi-IN", True, 52, "M", "surgeon", "hernia_repair", "post_surgery", ["surg_wound", "surg_better"]),
    ("Sneha Reddy", "te-IN", False, 38, "F", "surgeon", "cholecystectomy", "post_surgery", ["surg_emergency"]),
    ("Anil Nair", "ml-IN", False, 61, "M", "endo", "diabetes_review", "chronic_diabetes", ["dm_missed", "dm_missed"]),
    ("Farhan Qureshi", "hi-IN", True, 47, "M", "endo", "diabetes_review", "chronic_diabetes", ["dm_good"]),
    ("Riya Banerjee", "bn-IN", False, 26, "F", "derma2", "derma_consult", "derma_week1", ["derma_book"]),
    ("Kiran Patel", "gu-IN", False, 44, "M", "derma2", "derma_procedure", "derma_week1", ["derma_good"]),
    ("Gurpreet Kaur", "pa-IN", False, 57, "F", "ortho", "knee_arthroscopy", "post_surgery", ["surg_pain"]),
    ("Deepa Iyer", "en-IN", False, 33, "F", "derma", "acne_treatment", "derma_week1", []),
    ("Vikas Sharma", "hi-IN", True, 45, "M", "surgeon", "minor_surgery", "post_surgery", []),
    ("Lakshmi Gowda", "kn-IN", False, 66, "F", "endo", "diabetes_new_diagnosis", "chronic_diabetes", []),
    ("Karthik Subramanian", "ta-IN", True, 31, "M", "derma2", "eczema_treatment", "derma_week1", []),
    ("Sunita Joshi", "mr-IN", False, 58, "F", "ortho", "knee_arthroscopy", "post_surgery", []),
    ("Abhishek Ghosh", "bn-IN", False, 39, "M", "surgeon", "appendectomy", "post_surgery", []),
]

# Scripted synthetic patient replies for the offline agent (English; consent first).
SCRIPTS: dict[str, list[str]] = {
    "derma_good": ["yes", "better", "2", "no", "no", "no", "all", "a little dryness", "no", "no that's all"],
    "derma_infected": ["yes", "worse", "8", "yes there is swelling", "yes", "yes I have fever", "some, I forgot a few",
                       "burning", "yes", "option 1", "no"],
    "derma_book": ["yes", "same", "5", "no", "no", "no", "all", "no", "yes", "two", "no thanks"],
    "surg_good": ["yes", "2", "better", "no", "clean and dry", "walking normally", "no", "all", "no", "nothing else"],
    "surg_wound": ["yes", "6", "worse", "no", "there is some discharge", "a little", "no", "all", "yes", "first", "no"],
    "surg_better": ["yes", "3", "better", "no", "clean", "normal", "no", "all", "no", "no"],
    "surg_emergency": ["yes", "7", "worse", "I have chest pain and I can't breathe properly"],
    "surg_pain": ["yes", "9", "worse", "no", "red", "limited", "no", "some", "yes", "1", "no"],
    "dm_good": ["yes", "118", "no", "all", "good", "no", "no", "no"],
    "dm_missed": ["yes", "245", "no", "some, I missed doses", "partly", "no", "no", "no"],
}

DOCTORS = {
    "derma": ("Dr. Ananya Rao", "dermatology", 0),
    "surgeon": ("Dr. Vikram Iyer", "general_surgery", 1),
    "endo": ("Dr. Farah Siddiqui", "endocrinology", 1),
    "derma2": ("Dr. Rohan Das", "dermatology", 1),
    "ortho": ("Dr. Kavya Menon", "general_surgery", 1),
    "gp": ("Dr. Sameer Khan", "general_medicine", 1),
}


def _ist_to_utc(dt: datetime) -> datetime:
    """Naive IST wall-clock time to aware UTC."""
    return dt.replace(tzinfo=IST).astimezone(timezone.utc)


def _make_slots(db, doctor_ids: list[int], days: int = 10) -> None:
    today = datetime.now(IST).date()
    for d in range(days):
        day = today + timedelta(days=d)
        if day.weekday() == 6:
            continue
        for doctor_id in doctor_ids:
            for hour, minute in [(9, 30), (10, 0), (10, 30), (11, 0), (11, 30), (14, 0), (14, 30), (15, 0), (15, 30), (16, 30)]:
                start = _ist_to_utc(datetime(day.year, day.month, day.day, hour, minute))
                if start < utcnow():
                    continue
                status = "booked" if random.random() < 0.35 else "free"
                db.add(Slot(doctor_id=doctor_id, start=start, end=start + timedelta(minutes=20), status=status))


def build(history: bool = True) -> None:
    reset_db()
    with session_scope() as db:
        clinics = [
            Clinic(name="Twachaa Demo Skin Clinic", kind="clinic", city="Bengaluru"),
            Clinic(name="Aarogya Demo Hospital, Whitefield", kind="chain", city="Bengaluru"),
        ]
        db.add_all(clinics)
        db.commit()
        doctors = {}
        for key, (name, specialty, clinic_idx) in DOCTORS.items():
            doc = Doctor(clinic_id=clinics[clinic_idx].id, name=name, specialty=specialty)
            db.add(doc)
            doctors[key] = doc
        db.commit()
        _make_slots(db, [d.id for d in doctors.values()])

        from careloop.models import Patient

        plan_ids_with_history: list[tuple[int, list[str], int]] = []
        for i, (name, lang, codemix, age, sex, doc_key, procedure, pack_id, history_scripts) in enumerate(PATIENTS):
            doctor = doctors[doc_key]
            patient = Patient(clinic_id=doctor.clinic_id, name=name, phone=f"SYN-{1000 + i}", language=lang,
                              codemix=codemix, age=age, sex=sex)
            db.add(patient)
            db.commit()
            pack = get_pack(pack_id)
            n_prior = len(history_scripts)
            offset = pack.offset_days[-1]
            # Discharge far enough back that past check-ins happened and one more is due now.
            discharged = utcnow() - timedelta(days=offset * max(1, n_prior) + random.randint(0, 1), hours=random.randint(1, 6))
            enc = Encounter(patient_id=patient.id, doctor_id=doctor.id, specialty=doctor.specialty, procedure_type=procedure,
                            discharged_at=discharged, medications=MEDS[pack_id],
                            summary=f"{procedure.replace('_', ' ').title()} with {doctor.name}")
            db.add(enc)
            db.commit()
            for k, script in enumerate(history_scripts):
                plan = FollowupPlan(encounter_id=enc.id, patient_id=patient.id, pack_id=pack_id,
                                    due_at=discharged + timedelta(days=offset * (k + 1) if n_prior > 1 else offset),
                                    token=secrets.token_urlsafe(12))
                db.add(plan)
                db.commit()
                plan_ids_with_history.append((plan.id, SCRIPTS[script], n_prior - k))
            if not history_scripts:
                # Live demo: due now, waiting for the scheduler or the "Call now" button.
                db.add(FollowupPlan(encounter_id=enc.id, patient_id=patient.id, pack_id=pack_id,
                                    due_at=utcnow() + timedelta(minutes=2 + 3 * i), token=secrets.token_urlsafe(12)))
                db.commit()

    if history:
        asyncio.run(_run_history(plan_ids_with_history))


async def _run_history(plans: list[tuple[int, list[str], int]]) -> None:
    for plan_id, script, days_ago_rank in plans:
        conv, _ = await run_scripted_call(plan_id, script, offline=True)
        _backdate(conv.session.call.id, days=days_ago_rank * 2 + random.randint(0, 1))


def _backdate(call_id: int, days: int) -> None:
    shift = timedelta(days=days, hours=random.randint(0, 5))
    with session_scope() as db:
        call = db.get(Call, call_id)
        assert call
        for attr in ("rang_at", "started_at", "ended_at"):
            if getattr(call, attr):
                setattr(call, attr, getattr(call, attr) - shift)
        db.add(call)
        for model, field in ((Report, "created_at"), (TriageEvent, "created_at"), (MedAdherence, "recorded_at"), (Answer, "created_at")):
            for row in db.exec(select(model).where(model.call_id == call_id)).all():
                setattr(row, field, getattr(row, field) - shift)
                # Older alerts were already handled; the latest ones stay open on the board.
                if isinstance(row, TriageEvent) and days >= 4:
                    row.acked_by, row.acked_at = "nurse.demo", row.created_at + timedelta(minutes=12)
                db.add(row)
        db.commit()


if __name__ == "__main__":
    build()
