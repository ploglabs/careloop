"""Run a whole call against a scripted synthetic patient (no audio, no real people)."""

from careloop.agent.conversation import TextConversation
from careloop.db import session_scope
from careloop.models import Call, CallStatus, FollowupPlan, PlanStatus, utcnow


def open_call(plan_id: int, mode: str = "text") -> int:
    """Create a ringing call for a plan and return its id."""
    with session_scope() as db:
        plan = db.get(FollowupPlan, plan_id)
        assert plan is not None
        from careloop.models import Patient

        patient = db.get(Patient, plan.patient_id)
        assert patient is not None
        plan.status = PlanStatus.RINGING
        plan.attempts += 1
        call = Call(plan_id=plan.id, patient_id=plan.patient_id, mode=mode, status=CallStatus.RINGING,
                    language=patient.language, rang_at=utcnow())
        db.add(plan)
        db.add(call)
        db.commit()
        db.refresh(call)
        assert call.id is not None
        return call.id


async def run_scripted_call(plan_id: int, patient_lines: list[str], *, offline: bool = True) -> tuple[TextConversation, list[tuple[str, str]]]:
    call_id = open_call(plan_id)
    conv = TextConversation(call_id, offline=offline)
    log = [("agent", t) for t in conv.start()]
    for text in patient_lines:
        if conv.ended:
            break
        log.append(("patient", text))
        log.extend(("agent", t) for t in await conv.user(text))
    await conv.finish()
    return conv, log
