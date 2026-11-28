from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.enums import AssetCategory, AssetStatus, UserRole
from app.models.jurisdiction_node import NodeStatus
from app.services import compliance
from app.models.user import User
from app.schemas.asset import AssetCreate, AssetOut, AssetStatusUpdate
from app.services.audit import record_audit_event

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("/", response_model=AssetOut, status_code=201)
def create_asset(
    asset_in: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a newly sourced/claimed unclaimed asset. Starts in SOURCED
    status - it must pass do-no-harm and jurisdiction review (handled via
    PATCH /assets/{id}/status and the compliance fields) before a listing
    can be created from it."""
    asset = Asset(**asset_in.model_dump(), claimant_id=current_user.id)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/", response_model=List[AssetOut])
def list_assets(
    category: Optional[AssetCategory] = None,
    status: Optional[AssetStatus] = None,
    source_country: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Asset)
    if category:
        query = query.filter(Asset.category == category)
    if status:
        query = query.filter(Asset.status == status)
    if source_country:
        query = query.filter(Asset.source_country == source_country)
    return query.all()


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.patch("/{asset_id}/status", response_model=AssetOut)
def update_asset_status(
    asset_id: str,
    update: AssetStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restricted to compliance officers/admins - moves an asset through
    its review lifecycle (e.g. SOURCED -> UNDER_REVIEW -> VERIFIED)."""
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Not authorized to update asset status")

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    before_status = asset.status.value
    asset.status = update.status
    db.commit()
    db.refresh(asset)

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="asset",
        entity_id=asset.id,
        action="status_changed",
        before_state=f"status={before_status}",
        after_state=f"status={asset.status.value}",
    )

    return asset


class DoNoHarmReview(BaseModel):
    do_no_harm_cleared: Literal["pending", "cleared", "flagged"]
    reviewed_by: str          # the named person who made the call
    notes: Optional[str] = None


@router.patch("/{asset_id}/do-no-harm", response_model=AssetOut)
def review_do_no_harm(
    asset_id: str,
    review: DoNoHarmReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Records the Do No Harm screening result for an asset. This is the step a listing waits on: until an
    asset is 'cleared' here, no listing can be created from it. Admin or compliance officer only, a named
    reviewer is required, and the change is written to the audit log. Nothing sets this automatically."""
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Not authorized to review Do No Harm")
    if not review.reviewed_by.strip():
        raise HTTPException(status_code=422, detail="reviewed_by must name the person who made the review")
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    before = asset.do_no_harm_cleared
    asset.do_no_harm_cleared = review.do_no_harm_cleared
    db.commit()
    db.refresh(asset)
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="asset",
        entity_id=asset.id,
        action="do_no_harm_reviewed",
        before_state=f"do_no_harm_cleared={before}",
        after_state=f"do_no_harm_cleared={asset.do_no_harm_cleared}",
        notes=f"reviewed_by: {review.reviewed_by.strip()}. {review.notes or ''}".strip(),
    )
    return asset


class DoNoHarmBulk(BaseModel):
    reviewed_by: str                       # the named person making the call for this batch
    country_code: Optional[str] = None     # limit to one country
    category: Optional[AssetCategory] = None
    notes: Optional[str] = None
    limit: int = 500                       # per call, max 2000


@router.post("/do-no-harm/bulk")
def clear_do_no_harm_bulk(
    body: DoNoHarmBulk,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clears Do No Harm on every VERIFIED asset still 'pending' (optionally one country or category), in one
    call, under one named reviewer. Admin only. Skips, and reports, any asset whose country's legal-review node is
    RESTRICTED, SUSPENDED or has a recorded check failure, and anything already flagged. Every asset cleared gets
    its own audit entry. Clearing Do No Harm does not make a listing live: the country node must still be ACTIVE."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    if not body.reviewed_by.strip():
        raise HTTPException(status_code=422, detail="reviewed_by must name the person making this review")
    q = db.query(Asset).filter(Asset.status == AssetStatus.VERIFIED, Asset.do_no_harm_cleared == "pending")
    if body.country_code:
        q = q.filter(Asset.source_country == body.country_code.upper())
    if body.category:
        q = q.filter(Asset.category == body.category)
    assets = q.limit(min(max(body.limit, 1), 2000)).all()
    blocked = (NodeStatus.RESTRICTED, NodeStatus.SUSPENDED, NodeStatus.CHECK_FAILED)
    cleared, skipped = 0, []
    for a in assets:
        node = compliance.get_jurisdiction_node(db, a.source_country, a.source_region)
        if node is not None and node.status in blocked:
            skipped.append({"asset_id": a.id, "country": a.source_country, "reason": f"jurisdiction node is {node.status.value}"})
            continue
        a.do_no_harm_cleared = "cleared"
        record_audit_event(
            db, actor_user_id=current_user.id, actor_role=current_user.role.value, entity_type="asset",
            entity_id=a.id, action="do_no_harm_reviewed", before_state="do_no_harm_cleared=pending",
            after_state="do_no_harm_cleared=cleared",
            notes=f"bulk review, reviewed_by: {body.reviewed_by.strip()}. {body.notes or ''}".strip())
        cleared += 1
    db.commit()
    return {"considered": len(assets), "cleared": cleared, "skipped": len(skipped), "skipped_detail": skipped[:100],
            "more_remaining": len(assets) == min(max(body.limit, 1), 2000)}
