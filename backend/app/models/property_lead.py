"""PropertyLead - one property/owner record in the onboarding pipeline (see services/lead_engine.py)."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.core.database import Base

LEAD_STATUSES = ("new", "contacted", "onboarded", "do_not_contact")


class PropertyLead(Base):
    __tablename__ = "property_leads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dedupe_key = Column(String, nullable=False, unique=True, index=True)
    owner_name = Column(String, nullable=True)
    address = Column(String, nullable=True)
    mailing_address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True, index=True)
    zip = Column(String, nullable=True)
    county = Column(String, nullable=True, index=True)
    parcel_id = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    assessed_value = Column(Float, nullable=True)
    mortgage_balance = Column(Float, nullable=True)
    amount_owed = Column(Float, nullable=True)
    property_type = Column(String, nullable=True)
    flags = Column(Text, nullable=False, default="")        # ';'-joined distress flags
    score = Column(Integer, nullable=False, default=0, index=True)
    status = Column(String, nullable=False, default="new", index=True)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
