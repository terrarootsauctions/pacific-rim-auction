import pytest

from app.services import entities as e


def test_valid_handoff():
    assert e.validate_handoff(e.UMBRELLA, e.TERRAROOTS, "  parcel 12 ") == "parcel 12"


def test_same_entity_refused():
    with pytest.raises(ValueError):
        e.validate_handoff(e.TERRAROOTS, e.TERRAROOTS)


def test_coin_exchange_and_unknown_refused():
    for bad in ("pacific_rim_coin_exchange", "coin_exchange", "acme"):
        with pytest.raises(ValueError):
            e.validate_handoff(e.UMBRELLA, bad)


def test_default_entity_is_marketplace():
    assert e.entity_for_listing(None) == e.MARKETPLACE
    assert e.entity_for_listing(e.TERRAROOTS) == e.TERRAROOTS
