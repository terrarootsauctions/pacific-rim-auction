from datetime import datetime, timedelta

from app.services import governance as g

NOW = datetime(2026, 11, 24, 12, 0)
SCOPE = {"actions": ["PLACE_BID"], "limit_minor": 100000, "expires_at": NOW + timedelta(days=1)}


def test_no_scope_no_freeze_allows():
    assert g.evaluate(False, None, "CREATE_LISTING", None, NOW) == (True, None)


def test_freeze_blocks_everything_even_in_scope():
    ok, why = g.evaluate(True, SCOPE, "PLACE_BID", 5, NOW)
    assert not ok and why.startswith("FROZEN")


def test_scope_action_limit_and_expiry():
    assert g.evaluate(False, SCOPE, "PLACE_BID", 100000, NOW)[0]
    assert g.evaluate(False, SCOPE, "PLACE_BID", 100001, NOW)[1].startswith("OVER_LIMIT")
    assert g.evaluate(False, SCOPE, "CREATE_LISTING", None, NOW)[1].startswith("OUT_OF_SCOPE")
    later = NOW + timedelta(days=1)
    assert g.evaluate(False, SCOPE, "PLACE_BID", 1, later)[1].startswith("SCOPE_EXPIRED")


def test_scope_without_expiry_fails_closed():
    assert not g.evaluate(False, {"actions": ["PLACE_BID"], "limit_minor": None, "expires_at": None}, "PLACE_BID", 1, NOW)[0]


def test_validate_scope():
    assert g.validate_scope(["PLACE_BID"], 500, NOW + timedelta(hours=1), NOW) == []
    assert len(g.validate_scope([], 0, None, NOW)) == 3
    assert g.validate_scope(["PAY_OUT"], None, NOW + timedelta(hours=1), NOW)
    assert g.validate_scope(["PLACE_BID"], 1.5, NOW + timedelta(hours=1), NOW)
    assert g.validate_scope(["PLACE_BID"], True, NOW + timedelta(hours=1), NOW)
    assert g.validate_scope(["PLACE_BID"], None, NOW - timedelta(hours=1), NOW)
