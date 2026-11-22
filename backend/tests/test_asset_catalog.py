from app.models.enums import AssetCategory
from app.services import asset_catalog


def test_every_category_has_entries():
    for category in AssetCategory:
        assert asset_catalog.subtypes_for(category), category


def test_no_duplicate_entries():
    items = asset_catalog.all_subtypes()
    assert len(items) == len(set(items))


def test_catalog_covers_named_asset_kinds():
    text = " ".join(asset_catalog.all_subtypes()).lower()
    for word in ("jewelry", "yachts", "cruise ships", "luxury", "bank", "mineral"):
        assert word in text
