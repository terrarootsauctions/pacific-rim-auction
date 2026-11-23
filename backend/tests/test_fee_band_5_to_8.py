import pathlib
import re

_CONFIG = pathlib.Path(__file__).resolve().parents[1] / "app" / "core" / "config.py"
_SCHEMA = pathlib.Path(__file__).resolve().parents[1] / "app" / "schemas" / "listing.py"


def test_default_band_is_5_to_8_percent():
    text = _CONFIG.read_text()
    assert re.search(r"platform_fee_min: float = 0\.05\b", text)
    assert re.search(r"platform_fee_max: float = 0\.08\b", text)


def test_default_listing_rate_sits_inside_the_band():
    assert 'default=Decimal("0.05")' in _SCHEMA.read_text()
