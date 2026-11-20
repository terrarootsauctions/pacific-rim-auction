"""
Bid model - a bid placed on an auction-type listing.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Bid(Base):
    __tablename__ = "bids"

    id = Column(String, primary_key=True, default=gen_uuid)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    bidder_id = Column(String, ForeignKey("users.id"), nullable=False)

    amount_usd = Column(Float, nullable=False)
    placed_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("Listing", back_populates="bids")
    bidder = relationship("User", back_populates="bids")
