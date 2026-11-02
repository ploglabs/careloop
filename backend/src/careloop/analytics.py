"""Clinic-level analytics. The readmission-risk score is a transparent heuristic, not a model."""

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median
from typing import Any

from sqlmodel import Session, select

from careloop.models import Call, MedAdherence, Patient, Report, TriageEvent, Urgency, to_ist, utcnow


def readmission_risk(db: Session, patient: Patient) -> dict[str, Any]:
    since = utcnow() - timedelta(days=14)
    events = db.exec(select(TriageEvent).where(TriageEvent.patient_id == patient.id, TriageEvent.created_at >= since)).all()
    reports = db.exec(select(Report).where(Report.patient_id == patient.id).order_by(Report.created_at)).all()
    adherence = db.exec(select(MedAdherence).where(MedAdherence.patient_id == patient.id)).all()
    score, factors = 0, []
    levels = [e.level for e in events]
    if Urgency.EMERGENCY in levels:
        score += 40
        factors.append("emergency flag in last 14 days")
    elif Urgency.URGENT in levels:
        score += 25
        factors.append("urgent flag in last 14 days")
    reviews = levels.count(Urgency.REVIEW)
    if reviews:
        score += min(20, 5 * reviews)
        factors.append(f"{reviews} review flag(s)")
    missed = sum(1 for a in adherence if a.taken != "all")
    if missed:
        score += min(15, 5 * missed)
        factors.append("missed medicines")
    if (patient.age or 0) >= 65:
        score += 10
        factors.append("age 65+")
    scored = [r.recovery_score for r in reports if r.recovery_score is not None]
    if len(scored) >= 2 and scored[-1] < scored[-2]:
        score += 10
        factors.append("recovery score falling")
    score = min(100, score)
    band = "high" if score >= 60 else "medium" if score >= 30 else "low"
    return {"score": score, "band": band, "factors": factors, "heuristic": True}


def overview(db: Session, days: int = 30) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    calls = db.exec(select(Call).where(Call.rang_at >= since)).all()
    reports = db.exec(select(Report).where(Report.created_at >= since)).all()
    events = db.exec(select(TriageEvent).where(TriageEvent.created_at >= since)).all()
    adherence = db.exec(select(MedAdherence).where(MedAdherence.recorded_at >= since)).all()

    status_counts = Counter(c.status for c in calls)
    connected = sum(status_counts[s] for s in ("completed", "partial", "consent_declined"))
    flagged_by_day: dict[str, Counter] = defaultdict(Counter)
    for e in events:
        if e.level >= Urgency.REVIEW:
            flagged_by_day[to_ist(e.created_at).strftime("%Y-%m-%d")][Urgency(e.level).name] += 1
    today = to_ist(utcnow()).date()
    series = []
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        c = flagged_by_day.get(d, Counter())
        series.append({"date": d, "REVIEW": c["REVIEW"], "URGENT": c["URGENT"], "EMERGENCY": c["EMERGENCY"]})

    recovery: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_week: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in reports:
        if r.recovery_score is not None:
            week = to_ist(r.created_at).strftime("%G-W%V")
            by_week[(r.pack_id, week)].append(r.recovery_score)
    for (pack_id, week), vals in sorted(by_week.items(), key=lambda kv: kv[0][1]):
        recovery[pack_id].append({"week": week, "avg_score": round(sum(vals) / len(vals), 1), "n": len(vals)})

    latencies = [ms for c in calls for ms in (c.latencies_ms or [])]
    return {
        "window_days": days,
        "calls": {
            "total": len(calls),
            "by_status": dict(status_counts),
            "answer_rate": round(connected / len(calls), 3) if calls else None,
            "completion_rate": round(status_counts["completed"] / connected, 3) if connected else None,
        },
        "urgency": dict(Counter(Urgency(r.urgency).name for r in reports)),
        "flagged_series": series,
        "adherence_rate": round(sum(a.taken == "all" for a in adherence) / len(adherence), 3) if adherence else None,
        "languages": dict(Counter(c.language for c in calls)),
        "recovery_trend": recovery,
        "median_latency_ms": median(latencies) if latencies else None,
    }
