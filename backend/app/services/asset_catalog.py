"""
Asset catalog (PURE, no database): the kinds of unclaimed, dormant and
abandoned assets the platform sources, grouped under the ten
AssetCategory values. Used by the sourcing forms, search filters and
outreach targeting. The age of an asset is not limited: Asset.dormant_since_year
accepts any year, so records from 1845 through the present all fit.
"""
from typing import Dict, List

# Keys are the AssetCategory values (see app/models/enums.py). Plain strings
# keep this module free of database imports; a test checks the keys match.
CATALOG: Dict[str, List[str]] = {
    "real_property": [
        "Residential homes and condominiums",
        "Luxury and ultra-luxury estates",
        "Commercial buildings and offices",
        "Vacant land and farmland",
        "Tax-delinquent and tax-sale properties",
        "Foreclosure and bank-owned properties",
        "Abandoned and derelict properties",
        "Tax-sale and foreclosure surplus funds",
        "Zombie foreclosures (homes abandoned mid-foreclosure)",
        "Zombie titles (owner left, title never transferred)",
        "Vacant and blighted properties held by land banks",
    ],
    "financial": [
        "Dormant bank and credit union accounts",
        "Uncashed checks and final paychecks",
        "Stocks, dividends and bonds turned over to a state",
        "Unredeemed savings bonds",
        "Safe deposit box contents",
        "Dormant brokerage and investment accounts",
        "Dormant digital-asset exchange accounts",
        "Refunds and security deposits",
        "Class-action and settlement funds",
        "Gift cards, store credits and customer refunds",
        "Dormant payment-app balances and prepaid cards",
    ],
    "business_corporate": [
        "Assets of dissolved companies",
        "Unclaimed stock certificates and shares",
        "Abandoned business equipment and inventory",
        "Vendor and customer credit balances",
        "Assets of dormant zombie shell companies",
        "Airline, travel and telecom credits and deposits",
        "Retail and e-commerce customer credits",
        "Unclaimed supplier rebates and overpayments",
    ],
    "insurance_benefits": [
        "Life insurance proceeds",
        "Annuities",
        "Pension and retirement benefits",
        "Health and property insurance refunds",
        "Government benefit and tax refunds",
        "Unclaimed wages and payroll",
        "Healthcare and medical refunds",
        "Unemployment and workers' compensation payments",
    ],
    "transportation": [
        "Luxury yachts and motor vessels",
        "Cruise ships and large commercial vessels",
        "Aircraft",
        "Classic, exotic and luxury vehicles",
        "Abandoned and impounded vehicles",
        "Abandoned boats and marine equipment",
    ],
    "precious_collectible": [
        "Jewelry and watches",
        "Gold, silver and other precious metals",
        "Gemstones and diamonds",
        "Fine art and sculpture",
        "Coins, currency and stamps",
        "Antiques and rare collectibles",
    ],
    "natural_resource": [
        "Mineral and royalty rights",
        "Oil and gas interests",
        "Mining claims",
        "Timber and land-use rights",
        "Water rights",
    ],
    "intangible_ip": [
        "Patents",
        "Trademarks",
        "Copyrights and royalty streams",
        "Domain names",
        "Licensing rights",
    ],
    "estate_trust_probate": [
        "Intestate estates",
        "Unclaimed inheritances",
        "Unclaimed trust distributions",
        "Court-held probate funds",
    ],
    "public_utility": [
        "Utility deposits and refunds",
        "Government-held funds",
        "Court-registry funds",
        "Municipal and agency surplus property",
    ],
}


def subtypes_for(category) -> List[str]:
    key = getattr(category, "value", category)
    return list(CATALOG[key])


def all_subtypes() -> List[str]:
    return [item for items in CATALOG.values() for item in items]
