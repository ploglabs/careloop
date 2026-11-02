import secrets

from sqlmodel import select

from careloop import booking
from careloop.agent.simulate import open_call, run_scripted_call
from careloop.agent.session import CallSession
from careloop.db import session_scope
from careloop.models import (
    Answer, Appointment, Call, Consent, FollowupPlan, Outbox, Patient, PlanStatus, Report, Slot, TriageEvent, Urgency, utcnow,
)


def _plan(pack_id: str) -> int:
    """A fresh scheduled plan for an existing synthetic patient on this pack."""
    with session_scope() as db:
        template = db.exec(select(FollowupPlan).where(FollowupPlan.pack_id == pack_id)).first()
        assert template, pack_id
        plan = FollowupPlan(encounter_id=template.encounter_id, patient_id=template.patient_id, pack_id=pack_id,
                            due_at=utcnow(), token=secrets.token_urlsafe(12))
        db.add(plan)
        db.commit()
        return plan.id


async def test_routine_derma_call_completes_with_typed_answers():
    plan_id = _plan("derma_week1")
    conv, log = await run_scripted_call(plan_id, ["yes", "better", "two", "no", "no", "no", "all", "none", "no", "no"])
    s = conv.session
    assert s.ended and s.end_reason == "completed"
    assert s.answers["itching_score"] == 2 and s.answers["redness_trend"] == "better"
    assert s.level == Urgency.ROUTINE
    with session_scope() as db:
        report = db.exec(select(Report).where(Report.call_id == s.call.id)).one()
        assert report.status == "complete" and report.recovery_score and report.recovery_score > 80
        answers = db.exec(select(Answer).where(Answer.call_id == s.call.id)).all()
        assert {a.key for a in answers} == set(s.pack.keys)
        assert all(a.evidence_quote for a in answers)


async def test_emergency_mid_call_speaks_safety_line_and_alerts():
    plan_id = _plan("post_surgery")
    conv, log = await run_scripted_call(plan_id, ["yes", "4", "worse", "suddenly I have chest pain and feel breathless"])
    s = conv.session
    assert s.level == Urgency.EMERGENCY and s.end_reason == "emergency"
    agent_lines = [t for who, t in log if who == "agent"]
    assert any("108" in t for t in agent_lines), agent_lines
    with session_scope() as db:
        assert db.exec(select(TriageEvent).where(TriageEvent.call_id == s.call.id, TriageEvent.level == Urgency.EMERGENCY)).first()
        assert db.exec(select(Outbox).where(Outbox.channel == "nurse_alert", Outbox.patient_id == s.patient.id)).first()
        report = db.exec(select(Report).where(Report.call_id == s.call.id)).one()
        assert report.status == "partial" and report.urgency == Urgency.EMERGENCY


async def test_declined_consent_stores_no_health_data():
    plan_id = _plan("chronic_diabetes")
    conv, _ = await run_scripted_call(plan_id, ["no, not now"])
    s = conv.session
    assert s.consent is False and s.ended
    with session_scope() as db:
        assert db.exec(select(Answer).where(Answer.call_id == s.call.id)).first() is None
        assert db.exec(select(Report).where(Report.call_id == s.call.id)).first() is None
        consent = db.exec(select(Consent).where(Consent.call_id == s.call.id)).one()
        assert consent.granted is False


def test_answers_rejected_before_consent_and_validated():
    call_id = open_call(_plan("derma_week1"))
    s = CallSession(call_id)
    s.start("text")
    assert s.tool_record_answer("itching_score", 3, evidence_quote="three")["ok"] is False
    s.tool_record_consent(True)
    assert s.tool_record_answer("itching_score", 14, evidence_quote="fourteen")["ok"] is False
    assert s.tool_record_answer("redness_trend", "purple", evidence_quote="?")["ok"] is False
    assert s.tool_end_call("completed")["ok"] is False  # questions still open
    result = s.tool_record_answer("swelling", "yes", evidence_quote="yes swelling")
    assert result["ok"] and result["recorded"] == {"swelling": True}
    result = s.tool_record_answer("fever", True, evidence_quote="fever since yesterday")
    assert result.get("say_exactly")  # swelling + fever = URGENT rule
    assert s.level == Urgency.URGENT


def test_urgent_safety_line_not_repeated_for_same_level():
    call_id = open_call(_plan("post_surgery"))
    s = CallSession(call_id)
    s.start("text")
    s.tool_record_consent(True)
    first = s.on_user_text("there is pus coming out")
    second = s.on_user_text("also pus near the stitches")
    assert len(first.speak_now) == 1 and second.speak_now == []
    third = s.on_user_text("and now chest pain")
    assert len(third.speak_now) == 1  # rose to EMERGENCY


def test_booking_race_only_one_wins():
    with session_scope() as db:
        slot = db.exec(select(Slot).where(Slot.status == "free")).first()
        p1, p2 = db.exec(select(Patient).limit(2)).all()
        booking.book(db, slot_id=slot.id, patient_id=p1.id, call_id=None)
        try:
            booking.book(db, slot_id=slot.id, patient_id=p2.id, call_id=None)
            raise AssertionError("double booking")
        except booking.BookingError:
            pass
        assert len(db.exec(select(Appointment).where(Appointment.slot_id == slot.id)).all()) == 1


def test_reschedule_and_cancel_free_slots():
    call_id = open_call(_plan("derma_week1"))
    s = CallSession(call_id)
    s.start("text")
    s.tool_record_consent(True)
    slots = s.tool_check_slots()["slots"]
    assert 1 <= len(slots) <= 3
    booked = s.tool_book_slot(slots[0]["slot_id"])
    assert booked["ok"]
    moved = s.tool_reschedule(booked["appointment_id"], slots[1]["slot_id"])
    assert moved["ok"]
    with session_scope() as db:
        assert db.get(Slot, slots[0]["slot_id"]).status == "free"
        assert db.get(Slot, slots[1]["slot_id"]).status == "booked"
    assert s.tool_cancel_appointment(moved["appointment_id"])["ok"]
    with session_scope() as db:
        assert db.get(Slot, slots[1]["slot_id"]).status == "free"


def test_department_routing_flags_review():
    call_id = open_call(_plan("derma_week1"))
    s = CallSession(call_id)
    s.start("text")
    result = s.tool_suggest_department("my knee joint hurts when walking")
    assert result["department"] == "orthopedics"
    assert any(h.rule_id == "route_other_department" for h in s.hits)
    assert s.tool_suggest_department("I fainted this morning")["say_exactly"]


def test_no_answer_retry_then_fallback(monkeypatch):
    from careloop import scheduler
    from careloop.config import settings

    plan_id = _plan("post_surgery")
    for attempt in range(settings.max_attempts):
        call_id = scheduler.ring(plan_id)
        scheduler.mark_no_answer(call_id)
    with session_scope() as db:
        plan = db.get(FollowupPlan, plan_id)
        assert plan.status == PlanStatus.FALLBACK and plan.fallback_sent_at
        msgs = db.exec(select(Outbox).where(Outbox.patient_id == plan.patient_id, Outbox.channel == "whatsapp")).all()
        assert any(plan.token in m.body for m in msgs)
        assert len(db.exec(select(Call).where(Call.plan_id == plan_id, Call.status == "no_answer")).all()) == settings.max_attempts
