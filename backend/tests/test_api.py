from fastapi.testclient import TestClient
from sqlmodel import select

from careloop.api.app import app
from careloop.db import session_scope
from careloop.models import AuditLog, FollowupPlan, PlanStatus

client = TestClient(app)
ADMIN = {"X-User": "admin.demo", "X-Role": "admin"}


def test_health_and_meta():
    assert client.get("/api/health").json()["ok"]
    meta = client.get("/api/meta").json()
    assert len(meta["languages"]) == 10 and len(meta["packs"]) == 3


def test_today_board_and_flagged():
    today = client.get("/api/today").json()
    assert today["counts"]["pending_followups"] > 0
    assert today["counts"]["open_alerts"] > 0
    assert any(a["level"] == "EMERGENCY" for a in client.get("/api/alerts?status=all").json())
    flagged = client.get("/api/flagged?days=30").json()
    assert flagged["count"] >= 3
    assert all("risk" in p for p in flagged["patients"])


def test_role_required_for_clinical_data():
    assert client.get("/api/today", headers={"X-Role": "visitor"}).status_code == 403


def test_report_view_is_audited_and_fhir_exports():
    report = client.get("/api/today").json()["recent_reports"][0]
    detail = client.get(f"/api/reports/{report['id']}").json()
    assert detail["call"]["transcript"]
    bundle = client.get(f"/api/reports/{report['id']}/fhir").json()
    assert bundle["resourceType"] == "Bundle" and bundle["entry"][0]["resource"]["resourceType"] == "QuestionnaireResponse"
    audit = client.get("/api/audit", headers=ADMIN).json()
    assert any(a["action"] == "view_report" and a["entity_id"] == report["id"] for a in audit)


def test_ack_alert():
    alert = client.get("/api/alerts").json()[0]
    acked = client.post(f"/api/alerts/{alert['id']}/ack").json()
    assert acked["acked_by"] == "nurse.demo"


def test_analytics():
    data = client.get("/api/analytics").json()
    assert data["calls"]["total"] > 0 and len(data["flagged_series"]) == 14


def test_create_encounter_schedules_pack_offsets():
    meta = client.get("/api/meta").json()
    surgeon = next(d for d in meta["doctors"] if d["specialty"] == "general_surgery")
    res = client.post("/api/encounters", json={
        "name": "Test Synthetic Patient", "language": "ta-IN", "doctor_id": surgeon["id"],
        "procedure_type": "appendectomy", "medications": ["Paracetamol 650 mg"],
    }).json()
    assert len(res["plans"]) == 2  # day 1 and day 7


def test_text_call_over_websocket():
    from tests.test_calls import _plan

    with session_scope() as db:
        plan = db.get(FollowupPlan, _plan("chronic_diabetes"))
        token = plan.token
    info = client.get(f"/api/call/{token}").json()
    assert info["answerable"] and info["first_name"]
    with client.websocket_connect(f"/api/call/{token}/text") as ws:
        first = ws.receive_json()
        assert first["type"] == "agent"
        replies = iter(["yes", "130", "no", "all", "good", "no", "no", "nothing else"])
        ws.send_json({"text": next(replies)})
        while (msg := ws.receive_json())["type"] != "ended":
            if msg["type"] == "agent":
                nxt = next(replies, None)
                if nxt:
                    ws.send_json({"text": nxt})
    with session_scope() as db:
        assert db.get(FollowupPlan, plan.id).status == PlanStatus.COMPLETED


def test_voice_offer_without_keys_returns_503():
    with session_scope() as db:
        token = db.exec(select(FollowupPlan).where(FollowupPlan.status == PlanStatus.SCHEDULED)).first().token
    res = client.post(f"/api/call/{token}/offer", json={"sdp": "x", "type": "offer"})
    assert res.status_code == 503
