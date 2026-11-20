"""
Shared enums used across the platform.
"""
import enum


class AssetCategory(str, enum.Enum):
    """The categories of dormant/unclaimed/abandoned assets the Pacific Rim
    Auctions umbrella sources/claims globally. REAL_PROPERTY is the only
    category that routes through TerraRoots Global Realty Solutions LLC
    (which holds claimed real property and feeds it onto the Pacific Rim
    Auctions LLC marketplace to be sold); all other categories are listed
    directly on the Pacific Rim Auctions LLC marketplace with no TerraRoots
    involvement."""
    REAL_PROPERTY = "real_property"
    FINANCIAL = "financial"
    BUSINESS_CORPORATE = "business_corporate"
    INSURANCE_BENEFITS = "insurance_benefits"
    TRANSPORTATION = "transportation"
    PRECIOUS_COLLECTIBLE = "precious_collectible"
    NATURAL_RESOURCE = "natural_resource"
    INTANGIBLE_IP = "intangible_ip"
    ESTATE_TRUST_PROBATE = "estate_trust_probate"
    PUBLIC_UTILITY = "public_utility"


class AssetStatus(str, enum.Enum):
    SOURCED = "sourced"               # identified, not yet verified
    UNDER_REVIEW = "under_review"     # compliance / legal review in progress
    VERIFIED = "verified"             # cleared for listing
    LISTED = "listed"                 # actively listed for sale/auction
    UNDER_CONTRACT = "under_contract" # offer accepted, pending close
    SOLD = "sold"
    REJECTED = "rejected"             # failed compliance or legal review
    WITHDRAWN = "withdrawn"


class ListingType(str, enum.Enum):
    AUCTION = "auction"
    FIXED_PRICE = "fixed_price"
    MARKETPLACE = "marketplace"  # buyer/seller negotiated, e.g. real estate marketplace


class InspectionType(str, enum.Enum):
    PROPERTY_CONDITION = "property_condition"
    AIR_QUALITY = "air_quality"
    MINERAL_RIGHTS = "mineral_rights"


class InspectionStatus(str, enum.Enum):
    REQUIRED = "required"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    DISCLOSED = "disclosed"  # completed AND disclosed to buyer


class UserRole(str, enum.Enum):
    BUYER = "buyer"
    SELLER = "seller"
    ADMIN = "admin"
    COMPLIANCE_OFFICER = "compliance_officer"
    INSPECTOR = "inspector"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"                # payment instruction issued, no bank credit yet
    FEE_COLLECTED = "fee_collected"    # First Hawaiian Bank confirmed the exact fee credit
    NEEDS_REVIEW = "needs_review"      # a credit arrived but amount/currency did not match
    REFUNDED = "refunded"
    FAILED = "failed"


class BankEventStatus(str, enum.Enum):
    APPLIED = "applied"        # matched a transaction and recorded as revenue
    NEEDS_REVIEW = "needs_review"  # matched a transaction but amount/currency differed
    UNMATCHED = "unmatched"    # no transaction carries this payment reference
