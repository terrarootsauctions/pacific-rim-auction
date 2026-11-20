"""
Asset model - represents a sourced/claimed unclaimed, dormant, or abandoned
asset, in any of the 9 categories the Pacific Rim Auctions umbrella works
across.

This is the "sourcing engine" record. Once VERIFIED, it can be attached to
a Listing (real_property -> passes through TerraRoots Global Realty
Solutions LLC, then listed on the Pacific Rim Auctions LLC real estate
marketplace; everything else -> listed directly on the Pacific Rim
Auctions LLC marketplace).
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import AssetCategory, AssetStatus


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=gen_uuid)

    category = Column(Enum(AssetCategory), nullable=False, index=True)
    status = Column(Enum(AssetStatus), default=AssetStatus.SOURCED, nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    source_country = Column(String, nullable=False)  # ISO country code - which jurisdiction's laws apply
    source_region = Column(String, nullable=True)     # state/province/etc.

    # How long it's been dormant/unclaimed. Supports the "196 years back" sourcing mandate.
    dormant_since_year = Column(Integer, nullable=True)
    years_dormant = Column(Integer, nullable=True)

    estimated_value_usd = Column(Float, nullable=True)

    # Chain of custody / provenance notes - critical for legal defensibility
    # since Pacific Rim Auctions claims no legal ties to underlying ownership disputes.
    provenance_notes = Column(Text, nullable=True)

    # Compliance flags
    do_no_harm_cleared = Column(String, default="pending")  # pending | cleared | flagged
    jurisdiction_cleared = Column(String, default="pending")  # pending | cleared | flagged

    # The user that sourced/claims this asset. Must be a real ForeignKey: the
    # `claimant` relationship below cannot be configured without one.
    claimant_id = Column(String, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    claimant = relationship("User", back_populates="assets", foreign_keys=[claimant_id])
    listing = relationship("Listing", back_populates="asset", uselist=False)
