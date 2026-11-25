"""Applies the sanctions screen to a route. Does nothing unless SANCTIONS_SCREENING_ENABLED=true."""
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services import sanctions
from app.services.audit import record_audit_event


def enforce(db: Session, user: User, action: str, extra_names: Optional[Iterable[str]] = None) -> None:
    if not get_settings().sanctions_screening_enabled:
        return
    names = [user.full_name, *(extra_names or [])]
    result = sanctions.SCREENER.screen(names)
    if result["clear"]:
        return
    record_audit_event(
        db, actor_user_id=user.id, actor_role=user.role.value, entity_type="sanctions_screen",
        entity_id=user.id, action="blocked:" + action, before_state=None,
        after_state=result["reason"], notes="; ".join(
            f"{m['kind']} {m['sdn_name']} (ent {m['ent_num']})" for m in result["matches"]) or None)
    db.commit()
    raise HTTPException(status_code=423, detail=f"SANCTIONS_SCREEN: {result['reason']}. Held for review; no action taken.")
