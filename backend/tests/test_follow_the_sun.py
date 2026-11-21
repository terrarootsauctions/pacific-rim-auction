from datetime import datetime, timezone

from app.services import follow_the_sun as fts


def utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_country_zone_table():
    assert fts.country_timezones("JP") == ["Asia/Tokyo"]
    us = fts.country_timezones("us")
    assert "America/New_York" in us and "Pacific/Honolulu" in us
    assert fts.country_timezones("XX") == []


def test_daytime_boundaries_in_tokyo():
    assert fts.is_daytime("Asia/Tokyo", utc(2026, 11, 20, 22, 59)) is False  # 07:59 JST
    assert fts.is_daytime("Asia/Tokyo", utc(2026, 11, 20, 23, 0)) is True    # 08:00 JST
    assert fts.is_daytime("Asia/Tokyo", utc(2026, 11, 21, 10, 59)) is True   # 19:59 JST
    assert fts.is_daytime("Asia/Tokyo", utc(2026, 11, 21, 11, 0)) is False   # 20:00 JST


def test_honolulu_noon():
    assert fts.is_daytime("Pacific/Honolulu", utc(2026, 11, 20, 22, 0)) is True  # 12:00 HST


def test_next_daytime_start():
    # Tokyo evening: next day starts 08:00 JST = 23:00 UTC the same UTC date
    assert fts.next_daytime_start("Asia/Tokyo", utc(2026, 11, 20, 11, 0)) == utc(2026, 11, 20, 23, 0)
    # Already daytime: returns now
    now = utc(2026, 11, 20, 2, 0)  # 11:00 JST
    assert fts.next_daytime_start("Asia/Tokyo", now) == now
    # Before 08:00 local: opens later the same local day
    assert fts.next_daytime_start("Asia/Tokyo", utc(2026, 11, 20, 20, 0)) == utc(2026, 11, 20, 23, 0)


def test_sun_position_report():
    report = fts.sun_position_report(["JP", "US", "XX"], utc(2026, 11, 20, 15, 0))
    assert report["awake_now"] == ["US"]            # New York is 10:00
    assert [a["country_code"] for a in report["asleep"]] == ["JP"]  # Tokyo is 00:00
    assert report["not_in_iana_table"] == ["XX"]
    assert report["asleep"][0]["next_daytime_utc"] == utc(2026, 11, 20, 23, 0).isoformat()


def test_naive_datetime_is_treated_as_utc():
    assert fts.is_daytime("Asia/Tokyo", datetime(2026, 11, 20, 23, 0)) is True


def test_multi_zone_country_is_awake_if_any_zone_is():
    # 05:00 UTC: Sydney 16:00 (awake) even though Perth 13:00 / Lord Howe etc. vary
    assert fts.country_is_daytime("AU", utc(2026, 11, 20, 5, 0)) is True
