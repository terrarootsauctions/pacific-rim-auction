"""
Transaction model - the record of a marketplace sale and the platform fee
owed on it.

IMPORTANT: Revenue is only ever reported from transactions whose status is
FEE_COLLECTED, and a transaction only reaches that status when First Hawaiian
Bank confirms (via a signature-verified credit notification) that the exact
fee amount arrived. Nothing in this codebase reports revenue based on
listings created, bids placed, or any other non-bank-confirmed event.

The platform is receive-only: there is no payout, transfer or withdrawal
field because this platform never pays anyone.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import TransactionStatus


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=gen_uuid)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    buyer_id = Column(String, ForeignKey("users.id"), nullable=False)
    seller_id = Column(String, ForeignKey("users.id"), nullable=True)

    # Which entity earns the fee. Marketplace fees belong to Pacific Rim
    # Auctions LLC. Valid codes: PRA, PRA_LLC, TERRAROOTS_REALTY.
    entity_code = Column(String, nullable=False, default="PRA_LLC", index=True)

    # Money is whole cents (integers), never floats. The rate is whole basis
    # points (300 = 3.00%), clamped to the mandated 3-5% band.
    currency = Column(String(3), nullable=False, default="USD")
    sale_amount_minor = Column(BigInteger, nullable=False)
    platform_fee_rate_bps = Column(Integer, nullable=False)
    platform_fee_minor = Column(BigInteger, nullable=False)

    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)

    # Reference the payer must include on the bank transfer so the credit can
    # be matched to this transaction.
    payment_reference = Column(String, nullable=True, unique=True, index=True)
    # Bank's own reference for the confirmed credit.
    bank_reference = Column(String, nullable=True)
    received_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    listing = relationship("Listing")
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
