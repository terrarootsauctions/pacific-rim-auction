"""
Auction rules as PURE functions (no database, no clock of their own).

The database layer (auction_engine.py) loads the authoritative state, asks
these functions for a decision, and then applies the decision atomically.
Keeping the rules pure means every rule below is unit-tested without a
server. The browser is never authoritative: the server decides the validity
of a bid, the current bid, the closing time and the winner.

All money is whole cents (integers). Standard library only.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class AuctionState:
    is_live: bool
    compliance_hold: bool
    closed: bool
    seller_id: Optional[str]
    starts_at: Optional[datetime]
    closes_at: Optional[datetime]
    current_bid_minor: Optional[int]
    start_price_minor: Optional[int]
    currency: str = "USD"


@dataclass(frozen=True)
class BidderInfo:
    user_id: str
    kyc_verified: bool


@dataclass(frozen=True)
class BidDecision:
    accepted: bool
    reason: str                       # machine-readable code
    detail: str                       # human-readable explanation
    min_valid_bid_minor: Optional[int] = None
    new_closes_at: Optional[datetime] = None
    extended: bool = False


def min_valid_bid(state: AuctionState, increment_minor: int) -> int:
    """The smallest bid the server will accept right now."""
    if state.current_bid_minor is not None:
        return state.current_bid_minor + increment_minor
    floor = state.start_price_minor or 0
    return max(floor, increment_minor)


def decide_bid(
    state: AuctionState,
    bidder: BidderInfo,
    amount_minor: int,
    currency: str,
    now: datetime,
    increment_minor: int,
    snipe_window_seconds: int,
    snipe_extension_seconds: int,
) -> BidDecision:
    """Accept or reject one bid. First failing rule wins, and the rejection
    code says exactly which rule it was. `now` is the SERVER time."""
    if state.compliance_hold:
        return BidDecision(False, "COMPLIANCE_HOLD",
                           "This auction is on a compliance hold; bidding is paused.")
    if not state.is_live:
        return BidDecision(False, "NOT_LIVE", "Listing is not live.")
    if state.closed:
        return BidDecision(False, "AUCTION_CLOSED", "Auction has already closed.")
    if state.starts_at is not None and now < state.starts_at:
        return BidDecision(False, "NOT_STARTED", "Auction has not started yet.")
    if state.closes_at is not None and now >= state.closes_at:
        return BidDecision(False, "AUCTION_ENDED", "Auction closing time has passed.")
    if not bidder.kyc_verified:
        return BidDecision(False, "KYC_REQUIRED", "KYC verification required to bid.")
    if state.seller_id is not None and bidder.user_id == state.seller_id:
        return BidDecision(False, "SELLER_CANNOT_BID", "A seller cannot bid on their own listing.")
    if currency != state.currency:
        return BidDecision(False, "CURRENCY_MISMATCH",
                           f"Bids on this auction must be in {state.currency}.")
    if amount_minor <= 0:
        return BidDecision(False, "INVALID_AMOUNT", "Bid must be greater than zero.")

    floor = min_valid_bid(state, increment_minor)
    if amount_minor < floor:
        return BidDecision(False, "BID_TOO_LOW",
                           "Bid is below the minimum valid bid.", min_valid_bid_minor=floor)

    new_closes_at = state.closes_at
    extended = False
    if state.closes_at is not None:
        remaining = state.closes_at - now
        if remaining <= timedelta(seconds=snipe_window_seconds):
            new_closes_at = state.closes_at + timedelta(seconds=snipe_extension_seconds)
            extended = True

    return BidDecision(True, "ACCEPTED", "Bid accepted.",
                       min_valid_bid_minor=floor, new_closes_at=new_closes_at, extended=extended)


def pick_winner(bids: Iterable[Tuple[str, int, int]]) -> Optional[Tuple[str, int]]:
    """From (bidder_id, amount_minor, sequence) tuples, the winner is the
    highest amount; on an exact tie the EARLIER sequence wins. Returns
    (bidder_id, amount_minor) or None when there are no bids."""
    best = None
    for bidder_id, amount, seq in bids:
        if best is None or amount > best[1] or (amount == best[1] and seq < best[2]):
            best = (bidder_id, amount, seq)
    return None if best is None else (best[0], best[1])


def is_due_to_close(closed: bool, closes_at: Optional[datetime], now: datetime) -> bool:
    return (not closed) and closes_at is not None and now >= closes_at
