"""
Listing model - an asset made available for sale/auction on the platform.

For REAL_PROPERTY assets: the umbrella claims the property, it passes
through TerraRoots Global Realty Solutions LLC (the holding/pipeline
layer), and is then listed for sale on the Pacific Rim Auctions LLC
marketplace - the real estate marketplace covering residential,
commercial, ultra-luxury, distressed, and foreclosure properties. These
listings require property condition inspection, air quality assessment,
and mineral rights disclosure BEFORE the listing can go live, and all of
those results must be disclosed to the buyer prior to closing.

For all other asset categories, this is the direct marketplace/auction
listing path under the Pacific Rim Auctions umbrella: no physical
inspection requirement, no TerraRoots involvement.

Pacific Rim Auctions LLC takes no legal position in the underlying
buyer/seller real estate transaction - it only facilitates discovery,
transparency, and payment, and charges a 3-5% rolling platform fee on
closing costs.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import InspectionStatus, InspectionType, ListingType


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Listing(Base):
    __tablename__ = "listings"

    id = Column(String, primary_key=True, default=gen_uuid)

    asset_id = Column(String, ForeignKey("assets.id"), nullable=False, unique=True)
    seller_id = Column(String, ForeignKey("users.id"), nullable=True)

    listing_type = Column(Enum(ListingType), nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    asking_price_usd = Column(Float, nullable=True)
    current_bid_usd = Column(Float, nullable=True)

    # Platform fee actually applied to this listing, set within the 3-5% rolling range.
    platform_fee_rate = Column(Float, default=0.03)

    # Gate: real-property listings cannot go live until all required
    # inspections are COMPLETED and DISCLOSED. Checked by a service function,
    # not just this flag, but kept here for fast querying.
    is_live = Column(Boolean, default=False)

    requires_inspection = Column(Boolean, default=False)  # True for real_property assets

    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    asset = relationship("Asset", back_populates="listing")
    seller = relationship("User", back_populates="listings", foreign_keys=[seller_id])
    bids = relationship("Bid", back_populates="listing")
    inspections = relationship("Inspection", back_populates="listing")


class Inspection(Base):
    """A required disclosure item for real-property listings: property
    condition, air quality, or mineral rights. Must be COMPLETED and
    DISCLOSED to the buyer before closing."""

    __tablename__ = "inspections"

    id = Column(String, primary_key=True, default=gen_uuid)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)

    inspection_type = Column(Enum(InspectionType), nullable=False)
    status = Column(Enum(InspectionStatus), default=InspectionStatus.REQUIRED, nullable=False)

    inspector_name = Column(String, nullable=True)
    inspector_license_number = Column(String, nullable=True)
    report_summary = Column(Text, nullable=True)
    report_document_url = Column(String, nullable=True)

    completed_at = Column(DateTime, nullable=True)
    disclosed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("Listing", back_populates="inspections")
