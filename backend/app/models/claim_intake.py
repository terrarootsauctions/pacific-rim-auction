"""
ClaimIntake model - a request from an owner, heir or authorized
representative to have an unclaimed asset recovered with the platform's
help. Pacific Rim Auctions never owns the asset; this record tracks the
person's request, the review it passes through and the signed authorization
that must exist before anything is listed.

No government ID, bank account or card numbers are stored here (see
services/claim_intake.py). The signing events are the hash-chained evidence
from services/signing_chain.py, stored as JSON text.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text

from app.core.database import Base
from app.services.claim_intake import IntakeStatus, Relationship


def gen_uuid() -> str:
    return str(uuid.uuid4())


class ClaimIntake(Base):
    __tablename__ = "claim_intakes"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=True, index=True)

    claimant_name = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    relationship = Column(Enum(Relationship), nullable=False)
    country = Column(String, nullable=False, index=True)
    region = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    status = Column(Enum(IntakeStatus), default=IntakeStatus.SUBMITTED, nullable=False, index=True)

    # Set by compliance from the jurisdiction's legal review. Null means unknown,
    # and no fee can be agreed until it is set.
    legal_fee_cap_bps = Column(Integer, nullable=True)
    agreed_fee_bps = Column(Integer, nullable=True)

    authorization_document_sha256 = Column(String, nullable=True)
    signing_events = Column(Text, nullable=True)  # JSON list from signing_chain

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
