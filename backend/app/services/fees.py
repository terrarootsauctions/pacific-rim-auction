"""
Fee service - calculates the platform's rolling 3-5% fee in exact whole
cents. Kept as a small set of functions so the rolling-scale logic (currently
a flat caller-supplied rate clamped to the 3%-5% band) can evolve later
without touching every call site. All arithmetic is integer; see money.py.
"""
from app.core.config import get_settings
from app.services import money

settings = get_settings()


def fee_band_bps() -> tuple:
    """The mandated band as whole basis points (default 300 to 500)."""
    return (
        money.rate_to_bps(settings.platform_fee_min, 0, money.BPS_PER_UNIT),
        money.rate_to_bps(settings.platform_fee_max, 0, money.BPS_PER_UNIT),
    )


def clamp_fee_rate(requested_rate: float) -> float:
    """Ensure a fee rate always stays within the mandated band. Returns the
    rate as a fraction (e.g. 0.03) for storage on the listing."""
    low, high = fee_band_bps()
    return money.rate_to_bps(requested_rate, low, high) / money.BPS_PER_UNIT


def rate_bps(requested_rate) -> int:
    low, high = fee_band_bps()
    return money.rate_to_bps(requested_rate, low, high)


def calculate_platform_fee_minor(sale_minor: int, fee_rate) -> tuple:
    """Returns (fee_in_cents, rate_in_basis_points) for a sale in cents."""
    bps = rate_bps(fee_rate)
    return money.fee_minor(sale_minor, bps), bps
