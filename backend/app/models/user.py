"""
User model - shared across all three entities (the Pacific Rim Auctions
umbrella, Pacific Rim Auctions LLC, and TerraRoots Global Realty Solutions
LLC). One account, one identity, used everywhere.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import UserRole


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.BUYER, nullable=False)

    country = Column(String, nullable=True)  # ISO country code; for jurisdiction/compliance routing
    is_active = Column(Boolean, default=True)
    kyc_verified = Column(Boolean, default=False)  # gate for bidding/selling

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assets = relationship("Asset", back_populates="claimant", foreign_keys="Asset.claimant_id")
    listings = relationship("Listing", back_populates="seller", foreign_keys="Listing.seller_id")
    bids = relationship("Bid", back_populates="bidder")
