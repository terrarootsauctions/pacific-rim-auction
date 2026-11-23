"""
LawfulBasis - a recorded legal basis for listing an asset: confirmed seller
title, a referenced government sale, or a referenced court order.
(Owner authorization is not recorded here; it comes from a signed
ClaimIntake.) A NEW table on purpose: create_all() creates new tables on
startup but never adds columns to existing live ones.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class LawfulBasis(Base):
    __tablename__ = "lawful_basis_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=False, index=True)
    basis = Column(String, nullable=False)  # seller_title | government_authority | court_order
    reference = Column(Text, nullable=True)  # case number, sale notice, order id
    seller_holds_title = Column(Boolean, nullable=False, default=False)
    recorded_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
