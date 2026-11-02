"""Patient-facing call endpoints, reached through the /call/<token> link.

The token is the only credential, so these endpoints reveal just a first name, the clinic
and the language. Voice runs over WebRTC (Pipecat SmallWebRTC); text runs over a WebSocket.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlmodel import Session, col, select

from careloop.agent.conversation import TextConversation
from careloop.agent.simulate import open_call
from careloop.api.deps import User, current_user
from careloop.config import settings
from careloop.db import get_session, session_scope
from careloop.languages import LANGUAGES, lang
from careloop.models import Call, CallStatus, Clinic, FollowupPlan, Patient, PlanStatus
from careloop.scheduler import mark_no_answer, ring

router = APIRouter(prefix="/api")

ANSWERABLE = {PlanStatus.SCHEDULED, PlanStatus.RINGING, PlanStatus.RETRY, PlanStatus.FALLBACK}


def _plan_by_token(db: Session, token: str) -> FollowupPlan:
    plan = db.exec(select(FollowupPlan).where(FollowupPlan.token == token)).first()
    if plan is None:
        raise HTTPException(404, "Unknown or expired link")
    return plan


def _ringing_call(db: Session, plan_id: int) -> Call | None:
    return db.exec(
        select(Call).where(Call.plan_id == plan_id, Call.status == CallStatus.RINGING).order_by(col(Call.rang_at).desc())
    ).first()


def _answer(token: str, mode: str, language: str | None) -> int:
    """Pick up the ringing call for this link, or open one (fallback link / manual start)."""
    with session_scope() as db:
        plan = _plan_by_token(db, token)
        if plan.status not in ANSWERABLE:
            raise HTTPException(409, "This follow-up is already done")
        existing = _ringing_call(db, plan.id)
        call_id = existing.id if existing else None
    if call_id is None:
        call_id = open_call(plan.id, mode=mode)
    with session_scope() as db:
        call = db.get(Call, call_id)
        assert call
        call.mode = mode
        if language in LANGUAGES:
            call.language = language
        db.add(call)
        db.commit()
    return call_id


@router.get("/call/{token}")
def call_info(token: str, db: Session = Depends(get_session)):
    plan = _plan_by_token(db, token)
    patient = db.get(Patient, plan.patient_id)
    assert patient
    clinic = db.get(Clinic, patient.clinic_id)
    ringing = _ringing_call(db, plan.id)
    return {
        "first_name": patient.name.split()[0],
        "clinic": clinic.name if clinic else "",
        "language": patient.language,
        "language_name": lang(patient.language).english_name,
        "languages": [{"code": l.code, "name": l.english_name, "native": l.native_name} for l in LANGUAGES.values()],
        "plan_status": plan.status,
        "ringing": ringing is not None,
        "answerable": plan.status in ANSWERABLE,
        "voice_enabled": settings.voice_enabled,
        "llm_enabled": settings.llm_enabled,
    }


@router.post("/plans/{plan_id}/ring")
def ring_now(plan_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)):
    plan = db.get(FollowupPlan, plan_id)
    if plan is None:
        raise HTTPException(404)
    if plan.status not in ANSWERABLE:
        raise HTTPException(409, f"Plan is {plan.status}")
    if (existing := _ringing_call(db, plan.id)) is not None:
        return {"call_id": existing.id, "token": plan.token}
    return {"call_id": ring(plan_id), "token": plan.token}


@router.post("/call/{token}/decline")
def decline(token: str, db: Session = Depends(get_session)):
    plan = _plan_by_token(db, token)
    if (call := _ringing_call(db, plan.id)) is not None:
        mark_no_answer(call.id)
    return {"ok": True}


@router.websocket("/call/{token}/text")
async def text_call(ws: WebSocket, token: str):
    await ws.accept()
    language = ws.query_params.get("lang")
    offline = ws.query_params.get("offline") == "1" or None
    try:
        call_id = _answer(token, "text", language)
    except HTTPException as e:
        await ws.send_json({"type": "error", "text": e.detail})
        await ws.close()
        return
    conv = TextConversation(call_id, offline=offline)
    try:
        for t in conv.start():
            await ws.send_json({"type": "agent", "text": t})
        while not conv.ended:
            msg = await ws.receive_json()
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            await ws.send_json({"type": "typing"})
            for t in await conv.user(text):
                await ws.send_json({"type": "agent", "text": t})
        await ws.send_json({"type": "ended"})
    except WebSocketDisconnect:
        logger.info(f"text call {call_id}: patient left")
    except Exception as e:
        logger.exception(f"text call {call_id} failed: {e}")
        try:
            await ws.send_json({"type": "error", "text": "Something went wrong. Your care team will call you."})
        except Exception:
            pass
    finally:
        await conv.finish()
        try:
            await ws.close()
        except Exception:
            pass


# ------------------------------------------------------------------ WebRTC voice

_webrtc_handler = None


def _handler():
    global _webrtc_handler
    if _webrtc_handler is None:
        from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler

        _webrtc_handler = SmallWebRTCRequestHandler()
    return _webrtc_handler


async def close_webrtc() -> None:
    if _webrtc_handler is not None:
        await _webrtc_handler.close()


@router.post("/call/{token}/offer")
async def offer(token: str, request: Request, background_tasks: BackgroundTasks):
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest

    from careloop.agent.voice import run_voice_call, voice_ready

    ok, why = voice_ready()
    if not ok:
        raise HTTPException(503, f"Voice is not configured: {why}. Use text mode.")
    body = await request.json()
    language = request.query_params.get("lang")
    webrtc_request = SmallWebRTCRequest.from_dict({
        "sdp": body["sdp"], "type": body["type"], "pc_id": body.get("pc_id"),
        "restart_pc": body.get("restart_pc"), "request_data": body.get("request_data") or body.get("requestData"),
    })

    async def on_connection(connection):
        call_id = _answer(token, "voice", language)
        background_tasks.add_task(run_voice_call, call_id, connection)

    return await _handler().handle_web_request(request=webrtc_request, webrtc_connection_callback=on_connection)


@router.patch("/call/{token}/offer")
async def ice(token: str, request: Request):
    from pipecat.transports.smallwebrtc.request_handler import IceCandidate, SmallWebRTCPatchRequest

    body = await request.json()
    await _handler().handle_patch_request(SmallWebRTCPatchRequest(
        pc_id=body["pc_id"], candidates=[IceCandidate(**c) for c in body.get("candidates", [])],
    ))
    return {"ok": True}

