"""
Algorithm Fusion: the live auction engine (database layer).

All decisions come from auction_rules.decide_bid (pure, unit-tested); this
layer loads authoritative state, applies the decision atomically, and writes
the Memory Lock record IN THE SAME TRANSACTION. Atomicity:

  * the listing row is locked (SELECT ... FOR UPDATE on Postgres), so two
    simultaneous bids are processed one after the other, never together;
  * the idempotency key is unique per bidder, so retries return the
    original result and never create a second bid;
  * the bid, the new current bid, the sequence, any anti-sniping extension
    and the Memory Lock records are committed together or not at all.

The browser is never authoritative: the server clock, server sequence and
server decision rule everything.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bid import Bid
from app.models.listing import Listing
from app.models.user import User
from app.services import auction_rules as rules
from app.services import evolution, memory_lock, money
from app.services.memory_lock import EventType


class AuctionError(Exception):
    def __init__(self, status_code: int, code: str, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra or {}


def _state(listing: Listing) -> rules.AuctionState:
    return rules.AuctionState(
        is_live=bool(listing.is_live),
        compliance_hold=bool(listing.compliance_hold),
        closed=listing.closed_at is not None,
        seller_id=listing.seller_id,
        starts_at=listing.starts_at,
        closes_at=listing.ends_at,
        current_bid_minor=listing.current_bid_minor,
        start_price_minor=listing.asking_price_minor,
        currency=listing.currency or "USD",
    )


def snapshot(db: Session, listing: Listing) -> Dict:
    """Authoritative public state of one auction."""
    params = evolution.get_params(db)
    closed = listing.closed_at is not None
    return {
        "listing_id": listing.id,
        "sequence": int(listing.auction_sequence or 0),
        "currency": listing.currency or "USD",
        "current_bid_minor": listing.current_bid_minor,
        "current_bid": money.format_minor(listing.current_bid_minor) if listing.current_bid_minor is not None else None,
        "min_valid_bid_minor": None if closed else rules.min_valid_bid(_state(listing), params["min_bid_increment_minor"]),
        "closes_at": listing.ends_at.isoformat() + "Z" if listing.ends_at else None,
        "closed": closed,
        "compliance_hold": bool(listing.compliance_hold),
        "winning_bid_minor": listing.winning_bid_minor if closed else None,
    }


def _bid_event_payload(listing: Listing, bid: Bid) -> Dict:
    return {
        "listing_id": listing.id, "bid_id": bid.id, "bidder_id": bid.bidder_id,
        "currency": bid.currency, "amount_minor": int(bid.amount_minor),
        "auction_sequence": int(bid.sequence),
    }


def place_bid(
    db: Session,
    listing_id: str,
    bidder: User,
    amount_minor: int,
    currency: str,
    idempotency_key: str,
    now: Optional[datetime] = None,
) -> Dict:
    """Process one live bid. Returns a dict with outcome, bid and the events
    to broadcast, or raises AuctionError for a rejection."""
    now = now or datetime.utcnow()

    # 1. Idempotency: a repeat returns the ORIGINAL transaction result.
    existing = (
        db.query(Bid)
        .filter(Bid.bidder_id == bidder.id, Bid.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        listing = db.get(Listing, existing.listing_id)
        return {"outcome": "duplicate", "bid": existing, "listing": listing, "extended": False, "events": []}

    # 2. Lock the auction row so simultaneous bids are strictly serialized.
    listing = db.query(Listing).filter(Listing.id == listing_id).with_for_update().first()
    if listing is None:
        raise AuctionError(404, "LISTING_NOT_FOUND", "Listing not found.")

    # 3. If the closing time already passed, close it now (authoritatively), then reject.
    if rules.is_due_to_close(listing.closed_at is not None, listing.ends_at, now):
        events = close_listing(db, listing, now)
        db.commit()
        raise AuctionError(409, "AUCTION_ENDED", "Auction closing time has passed.", {"events": events})

    params = evolution.get_params(db)
    decision = rules.decide_bid(
        _state(listing),
        rules.BidderInfo(user_id=bidder.id, kyc_verified=bool(bidder.kyc_verified)),
        amount_minor, currency, now,
        increment_minor=params["min_bid_increment_minor"],
        snipe_window_seconds=params["anti_snipe_window_seconds"],
        snipe_extension_seconds=params["anti_snipe_extension_seconds"],
    )

    if not decision.accepted:
        memory_lock.capture(
            db, EventType.BID_REJECTED,
            {"listing_id": listing.id, "bidder_id": bidder.id, "currency": currency,
             "amount_minor": amount_minor, "reason": decision.reason,
             "min_valid_bid_minor": decision.min_valid_bid_minor},
            auction_id=listing.id, actor_id=bidder.id,
            metadata={"idempotency_key": idempotency_key},
        )
        db.commit()
        status = {"COMPLIANCE_HOLD": 423, "KYC_REQUIRED": 403, "SELLER_CANNOT_BID": 403,
                  "BID_TOO_LOW": 422, "INVALID_AMOUNT": 422, "CURRENCY_MISMATCH": 422}.get(decision.reason, 409)
        raise AuctionError(status, decision.reason, decision.detail,
                           {"min_valid_bid_minor": decision.min_valid_bid_minor})

    # 4. Accept: assign the authoritative sequence and update state atomically.
    seq = int(listing.auction_sequence or 0) + 1
    bid = Bid(
        listing_id=listing.id, bidder_id=bidder.id, currency=currency,
        amount_minor=amount_minor, idempotency_key=idempotency_key, sequence=seq, placed_at=now,
    )
    try:
        db.add(bid)
        db.flush()
    except IntegrityError:
        # A concurrent request with the same key won the race: return its result.
        db.rollback()
        existing = (
            db.query(Bid)
            .filter(Bid.bidder_id == bidder.id, Bid.idempotency_key == idempotency_key)
            .first()
        )
        if existing is None:
            raise AuctionError(503, "TEMPORARY_FAILURE", "Please retry.")
        return {"outcome": "duplicate", "bid": existing, "listing": db.get(Listing, existing.listing_id),
                "extended": False, "events": []}

    listing.current_bid_minor = amount_minor
    listing.leading_bidder_id = bidder.id
    listing.auction_sequence = seq

    events: List[Dict] = []
    memory_lock.capture(
        db, EventType.BID_ACCEPTED, _bid_event_payload(listing, bid),
        auction_id=listing.id, bid_id=bid.id, actor_id=bidder.id,
        metadata={"idempotency_key": idempotency_key},
    )
    events.append({"type": "BID_ACCEPTED", "sequence": seq,
                   "current_bid_minor": amount_minor, "currency": currency})

    if decision.extended:
        previous_close = listing.ends_at
        listing.ends_at = decision.new_closes_at
        listing.auction_sequence = seq + 1
        memory_lock.capture(
            db, EventType.AUCTION_EXTENDED,
            {"listing_id": listing.id, "previous_closes_at": previous_close.isoformat() + "Z",
             "new_closes_at": listing.ends_at.isoformat() + "Z", "auction_sequence": seq + 1},
            auction_id=listing.id, actor_id=bidder.id,
        )
        events.append({"type": "AUCTION_EXTENDED", "sequence": seq + 1,
                       "closes_at": listing.ends_at.isoformat() + "Z"})

    db.commit()
    db.refresh(bid)
    return {"outcome": "accepted", "bid": bid, "listing": listing,
            "extended": decision.extended, "events": events}


def close_listing(db: Session, listing: Listing, now: datetime) -> List[Dict]:
    """Close an auction and determine the winner on the server. Does NOT
    commit: the caller commits so the close and its Memory Lock records are
    saved together. Safe to call once; a closed listing is left alone."""
    if listing.closed_at is not None:
        return []

    bids = db.query(Bid).filter(Bid.listing_id == listing.id).all()
    winner = rules.pick_winner((b.bidder_id, int(b.amount_minor), int(b.sequence)) for b in bids)

    listing.closed_at = now
    listing.is_live = False
    seq = int(listing.auction_sequence or 0) + 1
    listing.auction_sequence = seq

    events = [{"type": "AUCTION_CLOSED", "sequence": seq}]
    memory_lock.capture(
        db, EventType.AUCTION_CLOSED,
        {"listing_id": listing.id, "closed_at": now.isoformat() + "Z", "auction_sequence": seq,
         "total_accepted_bids": len(bids)},
        auction_id=listing.id,
    )

    if winner is not None:
        listing.winner_id, listing.winning_bid_minor = winner
        seq += 1
        listing.auction_sequence = seq
        memory_lock.capture(
            db, EventType.WINNER_CONFIRMED,
            {"listing_id": listing.id, "winner_id": winner[0], "winning_bid_minor": winner[1],
             "currency": listing.currency or "USD", "auction_sequence": seq},
            auction_id=listing.id, actor_id=winner[0],
        )
        events.append({"type": "WINNER_CONFIRMED", "sequence": seq, "winning_bid_minor": winner[1]})
    return events


def close_due_auctions(db: Session, now: Optional[datetime] = None) -> List[Dict]:
    """Close every auction whose time has come. Safe to run on every instance
    at once: rows are locked (skipping ones another worker holds) and a
    closed auction is never closed twice."""
    now = now or datetime.utcnow()
    due_ids = [
        row[0]
        for row in db.query(Listing.id)
        .filter(Listing.closed_at.is_(None), Listing.ends_at.isnot(None), Listing.ends_at <= now)
        .all()
    ]
    all_events: List[Dict] = []
    for listing_id in due_ids:
        listing = (
            db.query(Listing).filter(Listing.id == listing_id)
            .with_for_update(skip_locked=True).first()
        )
        if listing is None or listing.closed_at is not None:
            db.rollback()
            continue
        events = close_listing(db, listing, now)
        db.commit()
        for e in events:
            all_events.append({**e, "listing_id": listing_id})
    return all_events
