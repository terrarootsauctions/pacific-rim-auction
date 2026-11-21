"""
Fee service - calculates the platform's rolling 3-5% fee.

Kept as a single function so the rolling-scale logic (currently a flat
caller-supplied rate clamped to [3%, 5%]) can be evolved later - e.g. to
scale by sale amount, asset category, or country - without touching every
call site.
"""
from app.core.config import get_settings

settings = get_settings()


def clamp_fee_rate(requested_rate: float) -> float:
    """Ensure the fee rate always stays within the mandated 3-5% band."""
    return max(settings.platform_fee_min, min(settings.platform_fee_max, requested_rate))


def calculate_platform_fee(sale_amount_usd: float, fee_rate: float) -> float:
    rate = clamp_fee_rate(fee_rate)
    return round(sale_amount_usd * rate, 2)
