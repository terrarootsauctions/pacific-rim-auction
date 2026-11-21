"""
Exact money math. Money is NEVER a binary float anywhere that matters.

All amounts are whole minor units (cents) held as Python integers. Fee rates
are whole basis points (300 = 3.00%). Conversion from decimal text uses
`decimal.Decimal`, which is exact, and rounding is always half-up.

Standard library only, so it can be tested without any other dependency.
"""
from decimal import Decimal, ROUND_HALF_UP

BPS_PER_UNIT = 10_000  # 100% = 10,000 basis points


def usd_to_minor(amount) -> int:
    """Convert a dollar amount (Decimal, int or numeric string) to whole
    cents. Refuses floats and anything with more than two decimal places, so
    a stray 0.1+0.2 style error can never enter the books."""
    if isinstance(amount, float):
        raise TypeError("Money must not be a binary float; pass a Decimal or string.")
    value = Decimal(str(amount))
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValueError("Amount has more than two decimal places.")
    return int(cents)


def format_minor(minor: int) -> str:
    """Whole cents to a fixed two-decimal string, e.g. 123456 -> '1234.56'."""
    sign = "-" if minor < 0 else ""
    whole, cents = divmod(abs(int(minor)), 100)
    return f"{sign}{whole}.{cents:02d}"


def rate_to_bps(rate, min_bps: int, max_bps: int) -> int:
    """Convert a fractional rate (0.03, '0.035' ...) to whole basis points,
    clamped into the mandated band."""
    bps = int((Decimal(str(rate)) * BPS_PER_UNIT).to_integral_value(rounding=ROUND_HALF_UP))
    return max(min_bps, min(max_bps, bps))


def fee_minor(sale_minor: int, rate_bps: int) -> int:
    """Platform fee in whole cents, rounded half-up, using integers only."""
    if sale_minor < 0 or rate_bps < 0:
        raise ValueError("Sale amount and rate must not be negative.")
    return (sale_minor * rate_bps + BPS_PER_UNIT // 2) // BPS_PER_UNIT
