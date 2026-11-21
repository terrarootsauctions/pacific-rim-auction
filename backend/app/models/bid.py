"""
Bid model - an ACCEPTED bid on an auction-type listing. Rejected bids are
not stored here; each rejection is recorded in the Memory Lock instead.

Money is whole cents. (bidder_id, idempotency_key) is unique, so a repeated
request (double-click, browser or network retry) can never create a second
bid; it returns the original result.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (
        UniqueConstraint("bidder_id", "idempotency_key", name="uq_bid_bidder_idempotency"),
    )

    id = Column(String, primary_key=True, default=gen_uuid)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False, index=True)
    bidder_id = Column(String, ForeignKey("users.id"), nullable=False)

    currency = Column(String(3), nullable=False, default="USD")
    amount_minor = Column(BigInteger, nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    sequence = Column(BigInteger, nullable=False)  # authoritative per-auction sequence
    placed_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("Listing", back_populates="bids")
    bidder = relationship("User", back_populates="bids")
