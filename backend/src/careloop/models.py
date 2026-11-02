"""Database tables.

Health answers live in `answers` (typed, with the patient's own words as evidence) and in
`reports.structured`. Raw audio is never stored unless CARELOOP_STORE_AUDIO is on.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from enum import IntEnum, StrEnum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


IST = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    """All stored datetimes are naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_ist(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)


class Urgency(IntEnum):
    """Ordered so that `max()` picks the most severe level."""

    ROUTINE = 0
    REVIEW = 1
    URGENT = 2
    EMERGENCY = 3

    @classmethod
    def parse(cls, value: "str | int | Urgency") -> "Urgency":
        if isinstance(value, Urgency):
            return value
        if isinstance(value, int):
            return cls(value)
        return cls[value.strip().upper()]


class PlanStatus(StrEnum):
    SCHEDULED = "scheduled"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    RETRY = "retry"
    FALLBACK = "fallback"
    COMPLETED = "completed"
    CLOSED = "closed"


class CallStatus(StrEnum):
    RINGING = "ringing"
    CONNECTED = "connected"
    NO_ANSWER = "no_answer"
    COMPLETED = "completed"
    PARTIAL = "partial"
    CONSENT_DECLINED = "consent_declined"


class Clinic(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    kind: str = "clinic"  # clinic | chain
    city: str = ""
    timezone: str = "Asia/Kolkata"


class Doctor(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    clinic_id: int = Field(foreign_key="clinic.id")
    name: str
    specialty: str


class Patient(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    clinic_id: int = Field(foreign_key="clinic.id")
    name: str
    # Synthetic placeholder only. Real phone numbers must never be stored in the demo.
    phone: str
    language: str = "en-IN"
    codemix: bool = False
    age: int | None = None
    sex: str | None = None


class Consent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    call_id: int | None = Field(default=None, foreign_key="call.id")
    purpose: str = "post_discharge_followup"
    language: str
    channel: str = "voice_agent"
    granted: bool
    created_at: datetime = Field(default_factory=utcnow)
    withdrawn_at: datetime | None = None


class Encounter(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    doctor_id: int = Field(foreign_key="doctor.id")
    specialty: str
    procedure_type: str
    summary: str = ""
    discharged_at: datetime
    medications: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class FollowupPlan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    encounter_id: int = Field(foreign_key="encounter.id")
    patient_id: int = Field(foreign_key="patient.id", index=True)
    pack_id: str
    due_at: datetime
    status: str = PlanStatus.SCHEDULED
    attempts: int = 0
    next_attempt_at: datetime | None = None
    # Opaque token for the patient call link (/call/<token>), also used by the fallback link.
    token: str = Field(index=True, unique=True)
    fallback_sent_at: datetime | None = None


class Call(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="followupplan.id", index=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    mode: str = "voice"  # voice | text
    status: str = CallStatus.RINGING
    language: str = "en-IN"
    rang_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    consent_given: bool | None = None
    transcript: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    latencies_ms: list[float] = Field(default_factory=list, sa_column=Column(JSON))


class Answer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    call_id: int = Field(foreign_key="call.id", index=True)
    key: str
    value: Any = Field(default=None, sa_column=Column(JSON))
    status: str = "answered"  # answered | declined | unclear
    confidence: float = 1.0
    evidence_quote: str = ""
    turn_index: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TriageEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    call_id: int | None = Field(default=None, foreign_key="call.id", index=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    level: int
    source: str  # lexicon | rule | llm_review | adherence | routing
    rule_id: str
    reason: str
    evidence: str = ""
    turn_index: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    acked_by: str | None = None
    acked_at: datetime | None = None
    assigned_to: str | None = None


class Report(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    call_id: int = Field(foreign_key="call.id", unique=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    pack_id: str
    status: str = "complete"  # complete | partial
    urgency: int = Urgency.ROUTINE
    summary_en: str = ""
    structured: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    recovery_score: float | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Slot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    start: datetime = Field(index=True)
    end: datetime
    status: str = "free"  # free | booked
    patient_id: int | None = Field(default=None, foreign_key="patient.id")


class Appointment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slot_id: int = Field(foreign_key="slot.id")
    patient_id: int = Field(foreign_key="patient.id", index=True)
    doctor_id: int = Field(foreign_key="doctor.id")
    call_id: int | None = Field(default=None, foreign_key="call.id")
    reason: str = ""
    source: str = "voice_agent"  # voice_agent | manual
    status: str = "booked"  # booked | cancelled | rescheduled
    created_at: datetime = Field(default_factory=utcnow)


class MedAdherence(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    call_id: int | None = Field(default=None, foreign_key="call.id")
    medication: str
    taken: str  # all | some | none
    reason: str = ""
    recorded_at: datetime = Field(default_factory=utcnow)


class Outbox(SQLModel, table=True):
    """Simulated outbound messages (WhatsApp, SMS, nurse pager). Nothing is actually sent."""

    id: int | None = Field(default=None, primary_key=True)
    channel: str  # whatsapp | sms | nurse_alert | pharmacy
    recipient: str
    body: str
    patient_id: int | None = Field(default=None, foreign_key="patient.id")
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    actor: str
    action: str
    entity: str
    entity_id: int | None = None
    at: datetime = Field(default_factory=utcnow)
