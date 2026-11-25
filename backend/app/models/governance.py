"""Single-row control state: the freeze switch and the optional permission scope."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class GovernanceState(Base):
    __tablename__ = "governance_state"

    id = Column(String, primary_key=True, default="singleton")
    frozen = Column(Boolean, nullable=False, default=False)
    frozen_by = Column(String, nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    frozen_reason = Column(Text, nullable=True)

    scope_actions = Column(String, nullable=True)       # comma separated, None = no scope set
    scope_limit_minor = Column(Integer, nullable=True)
    scope_expires_at = Column(DateTime, nullable=True)
    scope_set_by = Column(String, nullable=True)
    scope_set_at = Column(DateTime, nullable=True)
