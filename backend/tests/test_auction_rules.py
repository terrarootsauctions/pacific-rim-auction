from datetime import datetime, timedelta

from app.services.auction_rules import (
    AuctionState, BidderInfo, decide_bid, is_due_to_close, min_valid_bid, pick_winner,
)

NOW = datetime(2026, 11, 20, 12, 0, 0)
GOOD = BidderInfo(user_id="buyer1", kyc_verified=True)


def state(**kw):
    base = dict(
        is_live=True, compliance_hold=False, closed=False, seller_id="seller1",
        starts_at=NOW - timedelta(hours=1), closes_at=NOW + timedelta(hours=1),
        current_bid_minor=None, start_price_minor=10_000, currency="USD",
    )
    base.update(kw)
    return AuctionState(**base)


def decide(st, amount, bidder=GOOD, currency="USD", now=NOW):
    return decide_bid(st, bidder, amount, currency, now,
                      increment_minor=100, snipe_window_seconds=30, snipe_extension_seconds=30)


def test_first_bid_must_meet_starting_price():
    assert decide(state(), 9_999).reason == "BID_TOO_LOW"
    assert decide(state(), 10_000).accepted is True


def test_next_bid_must_clear_increment():
    st = state(current_bid_minor=20_000)
    assert decide(st, 20_000).reason == "BID_TOO_LOW"
    assert decide(st, 20_099).reason == "BID_TOO_LOW"
    d = decide(st, 20_100)
    assert d.accepted and d.min_valid_bid_minor == 20_100


def test_min_valid_bid_with_no_start_price_is_the_increment():
    assert min_valid_bid(state(start_price_minor=None), 100) == 100


def test_rejection_rules_each_have_their_own_code():
    assert decide(state(compliance_hold=True), 10_000).reason == "COMPLIANCE_HOLD"
    assert decide(state(is_live=False), 10_000).reason == "NOT_LIVE"
    assert decide(state(closed=True), 10_000).reason == "AUCTION_CLOSED"
    assert decide(state(starts_at=NOW + timedelta(minutes=1)), 10_000).reason == "NOT_STARTED"
    assert decide(state(closes_at=NOW), 10_000).reason == "AUCTION_ENDED"
    assert decide(state(), 10_000, bidder=BidderInfo("buyer1", False)).reason == "KYC_REQUIRED"
    assert decide(state(), 10_000, bidder=BidderInfo("seller1", True)).reason == "SELLER_CANNOT_BID"
    assert decide(state(), 10_000, currency="EUR").reason == "CURRENCY_MISMATCH"
    assert decide(state(), 0).reason == "INVALID_AMOUNT"


def test_compliance_hold_beats_everything_else():
    d = decide(state(compliance_hold=True, closed=True, is_live=False), 10_000)
    assert d.reason == "COMPLIANCE_HOLD"


def test_no_extension_when_plenty_of_time_left():
    d = decide(state(), 10_000)
    assert d.accepted and d.extended is False
    assert d.new_closes_at == NOW + timedelta(hours=1)


def test_anti_sniping_extends_inside_window():
    closes = NOW + timedelta(seconds=30)
    d = decide(state(closes_at=closes), 10_000)
    assert d.accepted and d.extended is True
    assert d.new_closes_at == closes + timedelta(seconds=30)


def test_anti_sniping_not_triggered_just_outside_window():
    closes = NOW + timedelta(seconds=31)
    d = decide(state(closes_at=closes), 10_000)
    assert d.accepted and d.extended is False


def test_bid_at_the_closing_instant_is_rejected():
    assert decide(state(closes_at=NOW), 10_000).reason == "AUCTION_ENDED"


def test_open_ended_listing_never_extends():
    d = decide(state(closes_at=None), 10_000)
    assert d.accepted and d.new_closes_at is None and d.extended is False


def test_pick_winner_highest_amount():
    assert pick_winner([("a", 100, 1), ("b", 300, 2), ("c", 200, 3)]) == ("b", 300)


def test_pick_winner_tie_goes_to_earlier_sequence():
    assert pick_winner([("late", 500, 9), ("early", 500, 2)]) == ("early", 500)


def test_pick_winner_none_when_no_bids():
    assert pick_winner([]) is None


def test_is_due_to_close():
    assert is_due_to_close(False, NOW, NOW) is True
    assert is_due_to_close(False, NOW + timedelta(seconds=1), NOW) is False
    assert is_due_to_close(True, NOW - timedelta(hours=1), NOW) is False
    assert is_due_to_close(False, None, NOW) is False
