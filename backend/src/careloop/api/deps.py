"""Demo auth: the dashboard sends X-User and X-Role headers. Replace with SSO in production."""

from dataclasses import dataclass

from fastapi import Header, HTTPException
from sqlmodel import Session

from careloop.models import AuditLog

STAFF_ROLES = {"nurse", "doctor", "admin"}


@dataclass
class User:
    name: str
    role: str


def current_user(x_user: str = Header("nurse.demo"), x_role: str = Header("nurse")) -> User:
    if x_role not in STAFF_ROLES:
        raise HTTPException(403, "Clinical data is restricted to care-team roles")
    return User(x_user, x_role)


def audit(db: Session, user: User, action: str, entity: str, entity_id: int | None) -> None:
    db.add(AuditLog(actor=f"{user.name} ({user.role})", action=action, entity=entity, entity_id=entity_id))
    db.commit()
