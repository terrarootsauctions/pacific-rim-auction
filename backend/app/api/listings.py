from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.enums import AssetStatus, InspectionStatus
from app.models.listing import Inspection, Listing
from app.models.user import User
from app.schemas.listing import (
    InspectionCreate,
    InspectionOut,
    InspectionUpdate,
    ListingCreate,
    ListingOut,
)
from app.services import compliance, money
from app.services import auction_engine, memory_lock, onetrust, publisher
from app.services.audit import record_audit_event
from app.services.governance_store import enforce
from app.services.fees import rate_bps

router = APIRouter(prefix="/listings", tags=["listings"])


@router.post("/", response_model=ListingOut, status_code=201)
def create_listing(
    listing_in: ListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce(db, "CREATE_LISTING")
    asset = db.query(Asset).filter(Asset.id == listing_in.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset.status != AssetStatus.VERIFIED:
        raise HTTPException(
            status_code=400,
            detail=f"Asset must be VERIFIED before listing (current status: {asset.status.value})",
        )

    cleared, reason = compliance.asset_cleared_for_listing(asset)
    if not cleared:
        raise HTTPException(status_code=400, detail=reason)

    requires_inspection = compliance.listing_requires_inspection(asset)

    listing = Listing(
        asset_id=asset.id,
        seller_id=current_user.id,
        listing_type=listing_in.listing_type,
        title=listing_in.title,
        description=listing_in.description,
        currency="USD",
        asking_price_minor=(
            money.usd_to_minor(listing_in.asking_price_usd)
            if listing_in.asking_price_usd is not None else None
        ),
        platform_fee_rate_bps=rate_bps(listing_in.platform_fee_rate),
        requires_inspection=requires_inspection,
        starts_at=listing_in.starts_at,
        ends_at=listing_in.ends_at,
        is_live=False,
    )
    db.add(listing)
    db.flush()  # assigns listing.id

    # Locked into the Memory Lock in the SAME transaction as the listing itself.
    created_payload = {
        "listing_id": listing.id, "asset_id": asset.id, "listing_type": listing.listing_type.value,
        "currency": listing.currency, "asking_price_minor": listing.asking_price_minor,
        "platform_fee_rate_bps": listing.platform_fee_rate_bps,
    }
    memory_lock.capture(db, memory_lock.EventType.LOT_CREATED, created_payload,
                        auction_id=listing.id, lot_id=asset.id, actor_id=current_user.id)
    if listing.listing_type.value == "auction":
        memory_lock.capture(db, memory_lock.EventType.AUCTION_CREATED, created_payload,
                            auction_id=listing.id, lot_id=asset.id, actor_id=current_user.id)
    db.commit()
    db.refresh(listing)

    if requires_inspection:
        compliance.create_required_inspections(db, listing)

    return listing


@router.get("/", response_model=List[ListingOut])
def list_listings(
    is_live: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Listing)
    if is_live is not None:
        query = query.filter(Listing.is_live == is_live)
    return query.all()


@router.get("/{listing_id}/auction-state")
def get_auction_state(listing_id: str, db: Session = Depends(get_db)):
    """Authoritative server-side state of the auction (sequence, current bid,
    minimum valid bid, closing time). Clients should treat this as the truth."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return auction_engine.snapshot(db, listing)


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: str, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("/{listing_id}/publish", response_model=ListingOut)
def publish_listing(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attempt to take a listing live. Blocked by the compliance gate if
    required inspections aren't completed+disclosed yet."""
    enforce(db, "PUBLISH_LISTING")
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    cleared, reason = compliance.listing_cleared_to_go_live(db, listing)
    if not cleared:
        raise HTTPException(status_code=400, detail=reason)

    # Hard-coded OneTrust compliance checkpoint (enforced when configured to be).
    ot_cleared, ot_reason = onetrust.check_listing(listing)
    if not ot_cleared:
        raise HTTPException(status_code=400, detail=ot_reason)

    asset = db.query(Asset).filter(Asset.id == listing.asset_id).first()
    gate_ok, gate_reasons, _basis = publisher.evaluate_asset_gate(db, asset)
    if not gate_ok:
        raise HTTPException(status_code=400, detail="; ".join(gate_reasons))

    listing.is_live = True
    memory_lock.capture(
        db, memory_lock.EventType.AUCTION_OPENED,
        {"listing_id": listing.id, "listing_type": listing.listing_type.value,
         "starts_at": listing.starts_at.isoformat() + "Z" if listing.starts_at else None,
         "closes_at": listing.ends_at.isoformat() + "Z" if listing.ends_at else None,
         "onetrust": ot_reason},
        auction_id=listing.id, actor_id=current_user.id,
    )
    db.commit()
    db.refresh(listing)

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="listing",
        entity_id=listing.id,
        action="published",
        before_state="is_live=False",
        after_state="is_live=True",
    )

    return listing


@router.post("/inspections", response_model=InspectionOut, status_code=201)
def create_inspection_record(
    inspection_in: InspectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(Listing).filter(Listing.id == inspection_in.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    inspection = Inspection(**inspection_in.model_dump())
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


@router.patch("/inspections/{inspection_id}", response_model=InspectionOut)
def update_inspection(
    inspection_id: str,
    update: InspectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move an inspection through REQUIRED -> SCHEDULED -> COMPLETED ->
    DISCLOSED. Only when DISCLOSED does it satisfy the buyer-disclosure
    mandate required before closing."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    from datetime import datetime

    before_status = inspection.status.value

    inspection.status = update.status
    if update.report_summary is not None:
        inspection.report_summary = update.report_summary
    if update.report_document_url is not None:
        inspection.report_document_url = update.report_document_url

    if update.status == InspectionStatus.COMPLETED:
        inspection.completed_at = datetime.utcnow()
    elif update.status == InspectionStatus.DISCLOSED:
        inspection.disclosed_at = datetime.utcnow()

    db.commit()
    db.refresh(inspection)

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="inspection",
        entity_id=inspection.id,
        action="status_changed",
        before_state=f"status={before_status}",
        after_state=f"status={inspection.status.value}",
    )

    return inspection


@router.get("/{listing_id}/inspections", response_model=List[InspectionOut])
def list_inspections_for_listing(listing_id: str, db: Session = Depends(get_db)):
    return db.query(Inspection).filter(Inspection.listing_id == listing_id).all()
