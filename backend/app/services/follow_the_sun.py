"""
Follow the Sun: which parts of the world are in daytime right now.

Uses the IANA time zone database (the same one every operating system uses)
and its official country-to-time-zone table (zone.tab). The platform runs
24/7/365, and this module answers: which reviewed countries are awake, which
are asleep and when they wake, so auctions, closings and outreach can be
timed to each country's day.

GROUND TRUTH RULES:
  - Only countries whose jurisdiction node is ACTIVE (legally reviewed and
    cleared) are ever counted as covered. A country in the time zone table
    that has not passed review is NOT part of the sun report.
  - If the time zone data cannot be found, this raises a clear error. It
    never guesses a time zone.

The core functions use only the standard library, so they can be tested
without a database. `follow_the_sun_report(db)` adds the database lookup.
"""
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from zoneinfo import TZPATH, ZoneInfo

# A country's "day" for platform purposes: 08:00 to 20:00 local time.
DAYTIME_START_HOUR = 8
DAYTIME_END_HOUR = 20


class TimeZoneDataError(RuntimeError):
    """The IANA time zone country table could not be found."""


def _find_zone_tab() -> str:
    for directory in TZPATH:
        candidate = Path(directory) / "zone.tab"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    try:  # fall back to the pip "tzdata" package used on minimal containers
        from importlib import resources

        return resources.files("tzdata.zoneinfo").joinpath("zone.tab").read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - any failure here means "not found"
        raise TimeZoneDataError(
            "IANA zone.tab not found. Install the 'tzdata' package or the "
            "system tzdata files. Time zones are never guessed."
        ) from exc


@lru_cache(maxsize=1)
def _country_zone_table() -> Dict[str, List[str]]:
    table: Dict[str, List[str]] = {}
    for line in _find_zone_tab().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        table.setdefault(parts[0].strip().upper(), []).append(parts[2].strip())
    return table


def country_timezones(country_code: str) -> List[str]:
    """IANA zones for an ISO 3166-1 alpha-2 country code. Empty list if the
    code is not in the IANA table."""
    return list(_country_zone_table().get(country_code.strip().upper(), []))


def _as_utc(now_utc: Optional[datetime]) -> datetime:
    if now_utc is None:
        return datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        return now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(timezone.utc)


def is_daytime(tz_name: str, now_utc: Optional[datetime] = None) -> bool:
    local = _as_utc(now_utc).astimezone(ZoneInfo(tz_name))
    return DAYTIME_START_HOUR <= local.hour < DAYTIME_END_HOUR


def next_daytime_start(tz_name: str, now_utc: Optional[datetime] = None) -> datetime:
    """The UTC moment this zone's day next begins (now, if it is already day)."""
    now = _as_utc(now_utc)
    zone = ZoneInfo(tz_name)
    local = now.astimezone(zone)
    if DAYTIME_START_HOUR <= local.hour < DAYTIME_END_HOUR:
        return now
    start_day = local.date() if local.hour < DAYTIME_START_HOUR else local.date() + timedelta(days=1)
    opens_local = datetime.combine(start_day, time(DAYTIME_START_HOUR, 0), tzinfo=zone)
    return opens_local.astimezone(timezone.utc)


def country_is_daytime(country_code: str, now_utc: Optional[datetime] = None) -> bool:
    """True if any time zone in the country is currently in daytime."""
    return any(is_daytime(tz, now_utc) for tz in country_timezones(country_code))


def next_open_for_country(country_code: str, now_utc: Optional[datetime] = None) -> Optional[datetime]:
    """The soonest moment daytime is under way anywhere in the country
    (None if the country is not in the IANA table)."""
    zones = country_timezones(country_code)
    if not zones:
        return None
    return min(next_daytime_start(tz, now_utc) for tz in zones)


def sun_position_report(country_codes: Iterable[str], now_utc: Optional[datetime] = None) -> dict:
    """Split the given countries into awake and asleep right now."""
    now = _as_utc(now_utc)
    awake: List[str] = []
    asleep: List[dict] = []
    unknown: List[str] = []
    for code in sorted({c.strip().upper() for c in country_codes}):
        opens = next_open_for_country(code, now)
        if opens is None:
            unknown.append(code)
        elif opens <= now:
            awake.append(code)
        else:
            asleep.append({"country_code": code, "next_daytime_utc": opens.isoformat()})
    asleep.sort(key=lambda row: row["next_daytime_utc"])
    return {
        "utc_now": now.isoformat(),
        "daytime_window_local": f"{DAYTIME_START_HOUR:02d}:00-{DAYTIME_END_HOUR:02d}:00",
        "awake_now": awake,
        "awake_count": len(awake),
        "asleep": asleep,
        "asleep_count": len(asleep),
        "not_in_iana_table": unknown,
    }


def follow_the_sun_report(db, now_utc: Optional[datetime] = None) -> dict:
    """The live sun report for the platform: only countries whose
    jurisdiction node is ACTIVE (legally reviewed) are counted."""
    from app.core.config import get_settings
    from app.models.jurisdiction_node import JurisdictionNode, NodeStatus

    rows = (
        db.query(JurisdictionNode.country_code)
        .filter(JurisdictionNode.status == NodeStatus.ACTIVE)
        .distinct()
        .all()
    )
    cleared: List[str] = [r[0] for r in rows]
    report = sun_position_report(cleared, now_utc)
    target = get_settings().country_target
    report.update(
        {
            "cleared_countries": len(cleared),
            "country_target": target,
            "countries_still_needing_review": max(target - len(cleared), 0),
            "note": (
                "Only countries whose jurisdiction node is ACTIVE are counted. "
                "A country is covered only after real legal review clears it."
            ),
        }
    )
    return report
