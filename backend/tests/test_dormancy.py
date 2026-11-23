from datetime import datetime

import pytest

from app.services import dormancy as d

Y2026 = datetime(2026, 11, 22)
Y2027 = datetime(2027, 1, 1)


def test_range_is_1845_through_current_year():
    assert d.validate_dormant_since_year(1845, Y2026) == 1845
    assert d.validate_dormant_since_year(2026, Y2026) == 2026
    assert d.validate_dormant_since_year(None, Y2026) is None
    for bad in (1844, 2027, 0, -5):
        with pytest.raises(ValueError):
            d.validate_dormant_since_year(bad, Y2026)


def test_range_rolls_into_2027_by_itself():
    with pytest.raises(ValueError):
        d.validate_dormant_since_year(2027, Y2026)
    assert d.validate_dormant_since_year(2027, Y2027) == 2027


def test_non_integers_are_refused():
    for bad in ("1998", 1998.5, True):
        with pytest.raises(ValueError):
            d.validate_dormant_since_year(bad, Y2026)


def test_years_dormant_is_calculated_and_rolls_forward():
    assert d.years_dormant(1990, Y2026) == 36
    assert d.years_dormant(1990, Y2027) == 37
    assert d.years_dormant(1845, Y2026) == 181
    assert d.years_dormant(2026, Y2026) == 0
    assert d.years_dormant(None, Y2026) is None


def test_years_dormant_never_negative():
    assert d.years_dormant(2030, Y2026) == 0


def test_decade_of():
    assert d.decade_of(1845) == 1840
    assert d.decade_of(1999) == 1990
    assert d.decade_of(2026) == 2020
