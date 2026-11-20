"""
Audit log service - the single, simple write path for recording every
consequential action on the platform.

This intentionally does ONE thing: insert a permanent record. It does
not delete, update, summarize, or judge. Reading/reporting on audit logs
belongs in si_orchestrator.py or admin.py, not here - this file's only
job is to make sure nothing consequential happens without a trace.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit_event(
    db: Session,
    actor_user_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    before_state: Optional[str] = None,
    after_state: Optional[str] = None,
    actor_role: Optional[str] = None,
    notes: Optional[str] = None,
) -> AuditLog:
    """Insert one permanent audit record. Never call this with a
    placeholder actor like 'system' - every consequential action in this
    platform is triggered by a real human, and that person's user_id
    belongs here."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_state=before_state,
        after_state=after_state,
        notes=notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
