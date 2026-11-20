from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.bid import Bid
from app.models.listing import Listing
from app.models.user import User
from app.schemas.bid import BidCreate, BidOut

router = APIRouter(prefix="/bids", tags=["bids"])


@router.post("/", response_model=BidOut, status_code=201)
def place_bid(
    bid_in: BidCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(Listing).filter(Listing.id == bid_in.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if not listing.is_live:
        raise HTTPException(status_code=400, detail="Listing is not live")
    if not current_user.kyc_verified:
        raise HTTPException(status_code=403, detail="KYC verification required to bid")

    if listing.current_bid_usd and bid_in.amount_usd <= listing.current_bid_usd:
        raise HTTPException(status_code=400, detail="Bid must exceed current bid")

    bid = Bid(listing_id=listing.id, bidder_id=current_user.id, amount_usd=bid_in.amount_usd)
    db.add(bid)
    listing.current_bid_usd = bid_in.amount_usd
    db.commit()
    db.refresh(bid)
    return bid


@router.get("/listing/{listing_id}", response_model=List[BidOut])
def get_bids_for_listing(listing_id: str, db: Session = Depends(get_db)):
    return db.query(Bid).filter(Bid.listing_id == listing_id).order_by(Bid.amount_usd.desc()).all()
