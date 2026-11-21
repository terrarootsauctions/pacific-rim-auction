from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.bid import Bid
from app.models.user import User
from app.schemas.bid import BidCreate, BidOut, BidResult
from app.services import auction_engine, money
from app.services.ratelimit import SlidingWindowLimiter
from app.services.realtime import manager

settings = get_settings()
router = APIRouter(prefix="/bids", tags=["bids"])

_limiter = SlidingWindowLimiter(settings.bid_rate_limit_count, settings.bid_rate_limit_window_seconds)


@router.post("/", response_model=BidResult, status_code=201)
async def place_bid(
    bid_in: BidCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Place a live bid. The server decides everything: validity, current bid,
    winner, closing time and anti-sniping extensions. Repeating a request with
    the same idempotency_key returns the original result (HTTP 200) and never
    creates a second bid."""
    if not _limiter.allow(current_user.id):
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED",
                                                     "message": "Too many bids; slow down."})

    amount_minor = money.usd_to_minor(bid_in.amount_usd)

    def run():
        return auction_engine.place_bid(
            db, bid_in.listing_id, current_user, amount_minor, bid_in.currency, bid_in.idempotency_key,
        )

    try:
        result = await run_in_threadpool(run)
    except auction_engine.AuctionError as exc:
        events = exc.extra.get("events")
        if events:
            await manager.publish_events(bid_in.listing_id, events)
        detail = {"code": exc.code, "message": exc.message,
                  **{k: v for k, v in exc.extra.items() if k != "events"}}
        raise HTTPException(status_code=exc.status_code, detail=detail)

    if result["outcome"] == "duplicate":
        response.status_code = 200
    else:
        await manager.publish_events(bid_in.listing_id, result["events"])

    listing = result["listing"]
    return BidResult(
        outcome=result["outcome"],
        bid=BidOut.model_validate(result["bid"]),
        auction_sequence=int(listing.auction_sequence or 0),
        closes_at=listing.ends_at,
        extended=result["extended"],
    )


@router.get("/listing/{listing_id}", response_model=List[BidOut])
def get_bids_for_listing(listing_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Bid)
        .filter(Bid.listing_id == listing_id)
        .order_by(Bid.amount_minor.desc(), Bid.sequence.asc())
        .all()
    )
