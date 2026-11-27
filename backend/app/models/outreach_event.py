"""
OutreachEvent - every event Reply.io (and Jason AI) pushes to the platform: replies, bounces,
opt-outs, finished sequences. Append-only. Kept separate from AuditLog on purpose: AuditLog entries
are real human actions, and these are events from an outside service.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.core.database import Base


class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)       # lower-cased; None if the payload carried none
    payload = Column(Text, nullable=False)                   # the raw JSON exactly as received
    received_at = Column(DateTime, default=datetime.utcnow, index=True)
