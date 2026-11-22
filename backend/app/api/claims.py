"""
Claim intake API.

  POST   /claims/                 signed-in user submits a claim request
  GET    /claims/mine             the user's own requests
  GET    /claims/                 admin / compliance officer: all requests
  PATCH  /claims/{id}/status      admin / compliance officer: move one step
  PATCH  /claims/{id}/fee         admin / compliance officer: set legal cap / agreed fee

Every consequential change is written to the audit log with the real human
actor. A request can reach AUTHORIZED only through a verified signature
chain (rules live in services/claim_intake.py).
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.claim_intake import ClaimIntake
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.claim_intake import ClaimFeeSet, ClaimIntakeCreate, ClaimIntakeOut, ClaimStatusUpdate
from app.services import claim_intake as rules
from app.services.audit import record_audit_event
from app.services.compliance import jurisdiction_node_cleared

router = APIRouter(prefix="/claims", tags=["claims"])


def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Admin or compliance officer access required")
    return current_user


def _get_or_404(db: Session, claim_id: str) -> ClaimIntake:
    claim = db.query(ClaimIntake).filter(ClaimIntake.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@router.post("/", response_model=ClaimIntakeOut, status_code=201)
def submit_claim(
    body: ClaimIntakeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        clean = rules.validate_intake(
            body.claimant_name, body.contact_email, body.country,
            body.relationship.value, body.description, body.region,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if body.asset_id and not db.query(Asset).filter(Asset.id == body.asset_id).first():
        raise HTTPException(status_code=404, detail="Asset not found")

    claim = ClaimIntake(user_id=current_user.id, asset_id=body.asset_id, **clean)
    db.add(claim)
    db.commit()
    db.refresh(claim)

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="claim_intake",
        entity_id=claim.id,
        action="submitted",
        after_state=f"status=submitted, country={claim.country}, relationship={claim.relationship.value}",
    )
    return claim


@router.get("/mine", response_model=List[ClaimIntakeOut])
def my_claims(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(ClaimIntake).filter(ClaimIntake.user_id == current_user.id).all()


@router.get("/", response_model=List[ClaimIntakeOut])
def all_claims(db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    return db.query(ClaimIntake).order_by(ClaimIntake.created_at.desc()).all()


@router.patch("/{claim_id}/status", response_model=ClaimIntakeOut)
def update_claim_status(
    claim_id: str,
    update: ClaimStatusUpdate,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_reviewer),
):
    claim = _get_or_404(db, claim_id)
    cleared, _ = jurisdiction_node_cleared(db, claim.country, claim.region)
    try:
        events = json.loads(claim.signing_events) if claim.signing_events else []
        new_status, reason = rules.advance_status(
            claim.status, update.status, cleared, events, claim.authorization_document_sha256
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    before = claim.status.value
    claim.status = new_status
    db.commit()
    db.refresh(claim)

    record_audit_event(
        db,
        actor_user_id=reviewer.id,
        actor_role=reviewer.role.value,
        entity_type="claim_intake",
        entity_id=claim.id,
        action="status_changed",
        before_state=f"status={before}",
        after_state=f"status={claim.status.value}",
        notes=reason,
    )
    return claim


@router.patch("/{claim_id}/fee", response_model=ClaimIntakeOut)
def set_claim_fee(
    claim_id: str,
    body: ClaimFeeSet,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_reviewer),
):
    claim = _get_or_404(db, claim_id)
    before = f"cap={claim.legal_fee_cap_bps}, agreed={claim.agreed_fee_bps}"

    if body.legal_fee_cap_bps is not None:
        if body.legal_fee_cap_bps < 0:
            raise HTTPException(status_code=422, detail="Legal fee cap cannot be negative.")
        claim.legal_fee_cap_bps = body.legal_fee_cap_bps
    if body.agreed_fee_bps is not None:
        try:
            claim.agreed_fee_bps = rules.validate_fee(body.agreed_fee_bps, claim.legal_fee_cap_bps)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    db.refresh(claim)

    record_audit_event(
        db,
        actor_user_id=reviewer.id,
        actor_role=reviewer.role.value,
        entity_type="claim_intake",
        entity_id=claim.id,
        action="fee_set",
        before_state=before,
        after_state=f"cap={claim.legal_fee_cap_bps}, agreed={claim.agreed_fee_bps}",
    )
    return claim
