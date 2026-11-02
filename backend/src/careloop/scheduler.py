"""Follow-up scheduling and the call state machine.

    scheduled → ringing → connected → completed | partial
                       ↘ no_answer → retry (after an interval) → … → fallback (WhatsApp/SMS link)

In the demo, "ringing" means the patient's phone page (/call/<token>) shows an incoming call.
No real phone call or message is ever placed; outbound messages land in the Outbox table.
"""

import secrets
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlmodel import Session, col, or_, select

from careloop import events
from careloop.agent.simulate import open_call
from careloop.config import settings
from careloop.db import session_scope
from careloop.languages import lang
from careloop.models import (
    Call,
    CallStatus,
    Encounter,
    FollowupPlan,
    Outbox,
    Patient,
    PlanStatus,
    utcnow,
)
from careloop.packs import pack_for_procedure


def create_plans_for_encounter(db: Session, encounter: Encounter) -> list[FollowupPlan]:
    """One plan per check-in offset of the matching pack (e.g. surgery: day 1 and day 7)."""
    pack = pack_for_procedure(encounter.procedure_type)
    if pack is None:
        return []
    plans = [
        FollowupPlan(
            encounter_id=encounter.id, patient_id=encounter.patient_id, pack_id=pack.id,
            due_at=encounter.discharged_at + timedelta(days=offset), token=secrets.token_urlsafe(12),
        )
        for offset in pack.offset_days
    ]
    db.add_all(plans)
    db.commit()
    return plans


def ring(plan_id: int) -> int:
    call_id = open_call(plan_id, mode="voice")
    with session_scope() as db:
        plan = db.get(FollowupPlan, plan_id)
        assert plan
        patient = db.get(Patient, plan.patient_id)
        assert patient
        events.publish("ring", {
            "plan_id": plan.id, "call_id": call_id, "token": plan.token, "patient_id": patient.id,
            "patient_name": patient.name, "language": patient.language, "attempt": plan.attempts,
        })
    logger.info(f"ringing plan {plan_id} (call {call_id})")
    return call_id


def _send_fallback(db: Session, plan: FollowupPlan, patient: Patient) -> None:
    link = f"{settings.public_web_url}/call/{plan.token}"
    first = patient.name.split()[0]
    body = (
        f"Hello {first}, we tried calling for your follow-up check-in. Tap to do it now in "
        f"{lang(patient.language).english_name} (2 minutes, voice or text): {link}"
    )
    db.add(Outbox(channel="whatsapp", recipient=patient.phone, patient_id=patient.id, body=body))
    db.add(Outbox(channel="sms", recipient=patient.phone, patient_id=patient.id, body=body))
    plan.fallback_sent_at = utcnow()
    plan.status = PlanStatus.FALLBACK
    events.publish("fallback", {"plan_id": plan.id, "patient_id": patient.id, "patient_name": patient.name, "link": link})


def mark_no_answer(call_id: int) -> None:
    with session_scope() as db:
        call = db.get(Call, call_id)
        if call is None or call.status != CallStatus.RINGING:
            return
        plan = db.get(FollowupPlan, call.plan_id)
        patient = db.get(Patient, call.patient_id)
        assert plan and patient
        call.status = CallStatus.NO_ANSWER
        call.ended_at = utcnow()
        if plan.attempts >= settings.max_attempts:
            _send_fallback(db, plan, patient)
        else:
            plan.status = PlanStatus.RETRY
            plan.next_attempt_at = utcnow() + timedelta(minutes=settings.retry_interval_minutes)
        db.add(call)
        db.add(plan)
        db.commit()
        events.publish("call", {"call_id": call.id, "patient_id": patient.id, "status": "no_answer",
                                "plan_status": plan.status, "attempts": plan.attempts})


def recover_orphaned_calls(older_than: timedelta = timedelta(0)) -> None:
    """Close calls left "connected" with no live session (server restart, crashed transport) so the plan can be rung again."""
    cutoff = utcnow() - older_than
    with session_scope() as db:
        orphans = db.exec(
            select(Call).where(Call.status == CallStatus.CONNECTED,
                               or_(col(Call.started_at).is_(None), col(Call.started_at) <= cutoff))
        ).all()
        for call in orphans:
            call.status = CallStatus.PARTIAL
            call.ended_at = utcnow()
            db.add(call)
            plan = db.get(FollowupPlan, call.plan_id)
            if plan and plan.status == PlanStatus.IN_PROGRESS:
                plan.status = PlanStatus.RETRY
                plan.next_attempt_at = utcnow() + timedelta(minutes=settings.retry_interval_minutes)
                db.add(plan)
            logger.warning(f"recovered orphaned call {call.id} (plan {call.plan_id})")
        db.commit()


def tick() -> None:
    recover_orphaned_calls(timedelta(seconds=settings.max_call_seconds * 2))
    now = utcnow()
    with session_scope() as db:
        due = db.exec(
            select(FollowupPlan).where(
                col(FollowupPlan.status).in_([PlanStatus.SCHEDULED, PlanStatus.RETRY]),
                FollowupPlan.due_at <= now,
                or_(col(FollowupPlan.next_attempt_at).is_(None), FollowupPlan.next_attempt_at <= now),
            )
        ).all()
        stale = db.exec(
            select(Call).where(Call.status == CallStatus.RINGING,
                               Call.rang_at <= now - timedelta(seconds=settings.ring_timeout_seconds))
        ).all()
    for call in stale:
        mark_no_answer(call.id)
    for plan in due:
        ring(plan.id)


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(tick, "interval", seconds=settings.scheduler_tick_seconds, max_instances=1, coalesce=True)
    scheduler.start()
    logger.info(f"scheduler running every {settings.scheduler_tick_seconds}s")
    return scheduler
