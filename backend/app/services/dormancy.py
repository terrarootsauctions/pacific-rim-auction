"""
Dormancy rules (PURE, no database): the year range the platform tracks and
how long an asset has been dormant.

The platform tracks unclaimed assets from EARLIEST_YEAR (1845) through the
current year. "Current year" is read from the clock each time, so the range
and every asset's years-dormant roll forward on their own: in 2027 the range
becomes 1845-2027 and an asset dormant since 1990 shows 37 years, with no
change to the code or the data.
"""
from datetime import datetime
from typing import Optional

EARLIEST_YEAR = 1845


def current_year(now: Optional[datetime] = None) -> int:
    return (now or datetime.utcnow()).year


def validate_dormant_since_year(year: Optional[int], now: Optional[datetime] = None) -> Optional[int]:
    """None is allowed (year unknown). Otherwise the year must fall between
    EARLIEST_YEAR and the current year, inclusive."""
    if year is None:
        return None
    if isinstance(year, bool) or not isinstance(year, int):
        raise ValueError("Dormant-since year must be a whole year, such as 1998.")
    latest = current_year(now)
    if year < EARLIEST_YEAR or year > latest:
        raise ValueError(f"Dormant-since year must be between {EARLIEST_YEAR} and {latest}.")
    return year


def years_dormant(dormant_since_year: Optional[int], now: Optional[datetime] = None) -> Optional[int]:
    """Whole years from the dormant-since year to the current year, never
    negative. None when the year is unknown."""
    if dormant_since_year is None:
        return None
    return max(0, current_year(now) - dormant_since_year)


def decade_of(year: int) -> int:
    return (year // 10) * 10
