"""
Asset catalog (PURE, no database): the kinds of unclaimed, dormant and
abandoned assets the platform sources, grouped under the ten
AssetCategory values. Used by the sourcing forms, search filters and
outreach targeting. The age of an asset is not limited: Asset.dormant_since_year
accepts any year, so records from 1845 through the present all fit.
"""
from typing import Dict, List

from app.models.enums import AssetCategory

CATALOG: Dict[AssetCategory, List[str]] = {
    AssetCategory.REAL_PROPERTY: [
        "Residential homes and condominiums",
        "Luxury and ultra-luxury estates",
        "Commercial buildings and offices",
        "Vacant land and farmland",
        "Tax-delinquent and tax-sale properties",
        "Foreclosure and bank-owned properties",
        "Abandoned and derelict properties",
        "Tax-sale and foreclosure surplus funds",
    ],
    AssetCategory.FINANCIAL: [
        "Dormant bank and credit union accounts",
        "Uncashed checks and final paychecks",
        "Stocks, dividends and bonds turned over to a state",
        "Unredeemed savings bonds",
        "Safe deposit box contents",
        "Dormant brokerage and investment accounts",
        "Dormant digital-asset exchange accounts",
        "Refunds and security deposits",
    ],
    AssetCategory.BUSINESS_CORPORATE: [
        "Assets of dissolved companies",
        "Unclaimed stock certificates and shares",
        "Abandoned business equipment and inventory",
        "Vendor and customer credit balances",
    ],
    AssetCategory.INSURANCE_BENEFITS: [
        "Life insurance proceeds",
        "Annuities",
        "Pension and retirement benefits",
        "Health and property insurance refunds",
        "Government benefit and tax refunds",
    ],
    AssetCategory.TRANSPORTATION: [
        "Luxury yachts and motor vessels",
        "Cruise ships and large commercial vessels",
        "Aircraft",
        "Classic, exotic and luxury vehicles",
        "Abandoned and impounded vehicles",
        "Abandoned boats and marine equipment",
    ],
    AssetCategory.PRECIOUS_COLLECTIBLE: [
        "Jewelry and watches",
        "Gold, silver and other precious metals",
        "Gemstones and diamonds",
        "Fine art and sculpture",
        "Coins, currency and stamps",
        "Antiques and rare collectibles",
    ],
    AssetCategory.NATURAL_RESOURCE: [
        "Mineral and royalty rights",
        "Oil and gas interests",
        "Mining claims",
        "Timber and land-use rights",
        "Water rights",
    ],
    AssetCategory.INTANGIBLE_IP: [
        "Patents",
        "Trademarks",
        "Copyrights and royalty streams",
        "Domain names",
        "Licensing rights",
    ],
    AssetCategory.ESTATE_TRUST_PROBATE: [
        "Intestate estates",
        "Unclaimed inheritances",
        "Unclaimed trust distributions",
        "Court-held probate funds",
    ],
    AssetCategory.PUBLIC_UTILITY: [
        "Utility deposits and refunds",
        "Government-held funds",
        "Court-registry funds",
        "Municipal and agency surplus property",
    ],
}


def subtypes_for(category: AssetCategory) -> List[str]:
    return list(CATALOG[category])


def all_subtypes() -> List[str]:
    return [item for items in CATALOG.values() for item in items]
