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
from app.services import memory_core, memory_lock

_COMPLIANCE_ENTITIES = {"jurisdiction_node", "asset", "inspection", "precedent"}


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
    db.flush()

    # Mirror into the Memory Lock in the SAME transaction, so every
    # consequential human action also lives in the signed, chained history.
    # Free-text notes are hashed, not copied, to keep personal text out of it.
    event_type = (
        memory_lock.EventType.COMPLIANCE_EVENT
        if entity_type in _COMPLIANCE_ENTITIES
        else memory_lock.EventType.ADMINISTRATIVE_ACTION
    )
    memory_lock.capture(
        db,
        event_type,
        {
            "audit_log_id": entry.id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "actor_role": actor_role,
            "before_state": before_state,
            "after_state": after_state,
            "notes_sha256": memory_core.sha256_hex(notes.encode("utf-8")) if notes else None,
        },
        actor_id=actor_user_id,
    )
    db.commit()
    db.refresh(entry)
    return entry
