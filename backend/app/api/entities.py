"""
Entity handoffs.

  POST /entities/handoff              record an asset passing between entities
  GET  /entities/asset/{asset_id}     handoff history for an asset

Admin and compliance officers only; every handoff is audited.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.entity_handoff import EntityHandoff
from app.models.enums import UserRole
from app.models.user import User
from app.services import entities
from app.services.audit import record_audit_event

router = APIRouter(prefix="/entities", tags=["entities"])


class HandoffCreate(BaseModel):
    asset_id: str
    from_entity: str
    to_entity: str
    note: Optional[str] = None


class HandoffOut(BaseModel):
    id: str
    asset_id: str
    from_entity: str
    to_entity: str
    note: Optional[str]

    model_config = {"from_attributes": True}


def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Admin or compliance officer access required")
    return current_user


@router.post("/handoff", response_model=HandoffOut, status_code=201)
def record_handoff(body: HandoffCreate, db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    if not db.query(Asset).filter(Asset.id == body.asset_id).first():
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        note = entities.validate_handoff(body.from_entity, body.to_entity, body.note or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    row = EntityHandoff(
        asset_id=body.asset_id, from_entity=body.from_entity, to_entity=body.to_entity,
        note=note or None, recorded_by=reviewer.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit_event(
        db, actor_user_id=reviewer.id, actor_role=reviewer.role.value, entity_type="asset",
        entity_id=body.asset_id, action="entity_handoff",
        after_state=f"{body.from_entity} -> {body.to_entity}",
    )
    return row


@router.get("/asset/{asset_id}", response_model=List[HandoffOut])
def handoffs_for_asset(asset_id: str, db: Session = Depends(get_db), _: User = Depends(require_reviewer)):
    return (
        db.query(EntityHandoff).filter(EntityHandoff.asset_id == asset_id)
        .order_by(EntityHandoff.created_at).all()
    )
