"""Admin-only controls: freeze / unfreeze and the expiring permission scope.
Every change is written to the permanent audit log under the acting admin."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.admin import require_admin
from app.core.database import get_db
from app.models.user import User
from app.services import governance
from app.services.audit import record_audit_event
from app.services.governance_store import get_state

router = APIRouter(prefix="/admin/governance", tags=["governance"])


class FreezeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ScopeIn(BaseModel):
    actions: List[str]
    expires_at: datetime
    limit_minor: Optional[int] = None


def _view(row):
    return {
        "frozen": bool(row.frozen), "frozen_by": row.frozen_by,
        "frozen_at": row.frozen_at.isoformat() if row.frozen_at else None, "frozen_reason": row.frozen_reason,
        "scope": None if not row.scope_actions else {
            "actions": row.scope_actions.split(","), "limit_minor": row.scope_limit_minor,
            "expires_at": row.scope_expires_at.isoformat() if row.scope_expires_at else None,
            "expired": bool(row.scope_expires_at and datetime.utcnow() >= row.scope_expires_at),
            "set_by": row.scope_set_by},
        "guarded_actions": list(governance.ACTIONS),
    }


def _audit(db, admin, action, before, after, notes=None):
    record_audit_event(db, actor_user_id=admin.id, actor_role=admin.role.value, entity_type="governance",
                       entity_id="singleton", action=action, before_state=before, after_state=after, notes=notes)


@router.get("")
def status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = get_state(db)
    db.commit()
    return _view(row)


@router.post("/freeze")
def freeze(body: FreezeIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = get_state(db)
    before = f"frozen={bool(row.frozen)}"
    row.frozen, row.frozen_by, row.frozen_at, row.frozen_reason = True, admin.id, datetime.utcnow(), body.reason
    db.commit()
    _audit(db, admin, "freeze", before, "frozen=True", body.reason)
    return _view(row)


@router.post("/unfreeze")
def unfreeze(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = get_state(db)
    before = f"frozen={bool(row.frozen)}"
    row.frozen = False
    db.commit()
    _audit(db, admin, "unfreeze", before, "frozen=False")
    return _view(row)


@router.put("/scope")
def set_scope(body: ScopeIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    problems = governance.validate_scope(body.actions, body.limit_minor, body.expires_at, datetime.utcnow())
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    row = get_state(db)
    before = row.scope_actions or "none"
    row.scope_actions = ",".join(body.actions)
    row.scope_limit_minor, row.scope_expires_at = body.limit_minor, body.expires_at
    row.scope_set_by, row.scope_set_at = admin.id, datetime.utcnow()
    db.commit()
    _audit(db, admin, "scope_set", before, f"{row.scope_actions}; limit={body.limit_minor}; expires={body.expires_at.isoformat()}")
    return _view(row)


@router.delete("/scope")
def clear_scope(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = get_state(db)
    before = row.scope_actions or "none"
    row.scope_actions = row.scope_limit_minor = row.scope_expires_at = row.scope_set_by = row.scope_set_at = None
    db.commit()
    _audit(db, admin, "scope_cleared", before, "none")
    return _view(row)
