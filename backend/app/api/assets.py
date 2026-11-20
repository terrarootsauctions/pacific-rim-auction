from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.enums import AssetCategory, AssetStatus, UserRole
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
