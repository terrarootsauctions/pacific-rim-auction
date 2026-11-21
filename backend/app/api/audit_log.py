from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.audit_log import AuditLogOut

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


def require_admin_or_compliance(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Admin or compliance officer access required")
    return current_user


@router.get("/", response_model=List[AuditLogOut])
def list_audit_entries(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_compliance),
):
    """Read-only. There is no update or delete endpoint for audit
    entries, by design - the whole point of this table is that it
    cannot be altered after the fact."""
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    return query.order_by(AuditLog.created_at.desc()).limit(500).all()


@router.get("/{entity_type}/{entity_id}", response_model=List[AuditLogOut])
def get_entity_history(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_compliance),
):
    """The full, permanent history for one specific thing - one
    jurisdiction node, one asset, one listing - in chronological order.
    This is what you'd hand a regulator or attorney who asks 'prove this
    was actually reviewed.'"""
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
