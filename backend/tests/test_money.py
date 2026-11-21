from decimal import Decimal

import pytest

from app.services import money


def test_usd_to_minor_is_exact():
    assert money.usd_to_minor(Decimal("250000.00")) == 25_000_000
    assert money.usd_to_minor("0.10") == 10
    assert money.usd_to_minor("19.99") == 1999
    assert money.usd_to_minor(5) == 500


def test_floats_are_refused():
    with pytest.raises(TypeError):
        money.usd_to_minor(0.1 + 0.2)


def test_more_than_two_decimals_refused():
    with pytest.raises(ValueError):
        money.usd_to_minor("10.005")


def test_format_minor():
    assert money.format_minor(123456) == "1234.56"
    assert money.format_minor(5) == "0.05"
    assert money.format_minor(0) == "0.00"
    assert money.format_minor(-250) == "-2.50"


def test_rate_to_bps_and_clamping():
    assert money.rate_to_bps(0.03, 300, 500) == 300
    assert money.rate_to_bps("0.035", 300, 500) == 350
    assert money.rate_to_bps(0.01, 300, 500) == 300   # below band, raised to 3%
    assert money.rate_to_bps(0.09, 300, 500) == 500   # above band, lowered to 5%
    # a float like 0.07 is converted through its decimal text, so no drift
    assert money.rate_to_bps(0.05, 300, 500) == 500


def test_fee_minor_exact_and_half_up():
    assert money.fee_minor(25_000_000, 300) == 750_000        # 3% of $250,000.00 = $7,500.00
    assert money.fee_minor(10_001, 300) == 300                # 300.03 rounds down
    assert money.fee_minor(10_017, 300) == 301                # 300.51 rounds up
    assert money.fee_minor(50, 300) == 2                      # 1.5 rounds half up to 2
    assert money.fee_minor(0, 300) == 0


def test_fee_has_no_float_drift_on_large_sale():
    # $48,765,432.10 at 4.25% (425 bps); float math can be a cent off here
    sale = money.usd_to_minor("48765432.10")
    assert money.fee_minor(sale, 425) == (sale * 425 + 5000) // 10000


def test_negative_inputs_refused():
    with pytest.raises(ValueError):
        money.fee_minor(-1, 300)
