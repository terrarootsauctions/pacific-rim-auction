import importlib.util
import pathlib

from app.services import asset_catalog

_ENUMS = pathlib.Path(__file__).resolve().parents[1] / "app" / "models" / "enums.py"
_spec = importlib.util.spec_from_file_location("pra_enums", _ENUMS)
_enums = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_enums)


def test_catalog_keys_match_asset_categories():
    assert set(asset_catalog.CATALOG) == {c.value for c in _enums.AssetCategory}


def test_every_category_has_entries():
    for category in _enums.AssetCategory:
        assert asset_catalog.subtypes_for(category), category


def test_no_duplicate_entries():
    items = asset_catalog.all_subtypes()
    assert len(items) == len(set(items))


def test_catalog_covers_named_asset_kinds():
    text = " ".join(asset_catalog.all_subtypes()).lower()
    for word in ("jewelry", "yachts", "cruise ships", "luxury", "bank", "mineral"):
        assert word in text
