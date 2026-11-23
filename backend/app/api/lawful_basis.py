"""
Lawful-basis records.

  POST /lawful-basis/                record seller title, a referenced government sale, or a referenced court order
  GET  /lawful-basis/asset/{asset_id}  what is on record for an asset

Admin and compliance officers only, because these records are legal facts
that an attorney verifies. Every record is written to the audit log.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.enums import UserRole
from app.models.lawful_basis import LawfulBasis
from app.models.user import User
from app.services import listing_gate
from app.services.audit import record_audit_event

router = APIRouter(prefix="/lawful-basis", tags=["lawful-basis"])


class LawfulBasisCreate(BaseModel):
    asset_id: str
    basis: str
    reference: Optional[str] = None


class LawfulBasisOut(BaseModel):
    id: str
    asset_id: str
    basis: str
    reference: Optional[str]
    seller_holds_title: bool

    model_config = {"from_attributes": True}


def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Admin or compliance officer access required")
    return current_user


@router.post("/", response_model=LawfulBasisOut, status_code=201)
def record_basis(body: LawfulBasisCreate, db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    if not db.query(Asset).filter(Asset.id == body.asset_id).first():
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        reference = listing_gate.validate_basis_record(body.basis, body.reference)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    row = LawfulBasis(
        asset_id=body.asset_id,
        basis=body.basis,
        reference=reference or None,
        seller_holds_title=(body.basis == listing_gate.BASIS_SELLER_TITLE),
        recorded_by=reviewer.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit_event(
        db,
        actor_user_id=reviewer.id,
        actor_role=reviewer.role.value,
        entity_type="asset",
        entity_id=body.asset_id,
        action="lawful_basis_recorded",
        after_state=f"basis={body.basis}, reference={'yes' if reference else 'none'}",
    )
    return row


@router.get("/asset/{asset_id}", response_model=List[LawfulBasisOut])
def basis_for_asset(asset_id: str, db: Session = Depends(get_db), _: User = Depends(require_reviewer)):
    return db.query(LawfulBasis).filter(LawfulBasis.asset_id == asset_id).all()
