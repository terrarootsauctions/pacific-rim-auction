"""Reads/writes the single control row and enforces it for the guarded routes."""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.governance import GovernanceState
from app.services import governance


def get_state(db: Session) -> GovernanceState:
    row = db.query(GovernanceState).filter(GovernanceState.id == "singleton").first()
    if row is None:
        row = GovernanceState(id="singleton", frozen=False)
        db.add(row)
        db.flush()
    return row


def scope_of(row: GovernanceState) -> Optional[dict]:
    if not row.scope_actions:
        return None
    return {"actions": [a for a in row.scope_actions.split(",") if a],
            "limit_minor": row.scope_limit_minor, "expires_at": row.scope_expires_at}


def enforce(db: Session, action: str, amount_minor: Optional[int] = None) -> None:
    """Call at the top of a guarded route. Raises 423 when blocked."""
    row = get_state(db)
    ok, reason = governance.evaluate(bool(row.frozen), scope_of(row), action, amount_minor, datetime.utcnow())
    if not ok:
        raise HTTPException(status_code=423, detail=reason)
