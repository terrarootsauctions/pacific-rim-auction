"""
AuditLog model - a permanent, append-only record of every consequential
human action on the platform: jurisdiction node reviews, asset status
changes, listing publication, inspection disclosure, and check failures.

This exists for one reason: so the platform's compliance claims ("do no
harm," "follow the laws of the land") are provable, not just asserted.
If a regulator, attorney, or the architect ever needs to confirm who
reviewed a jurisdiction, when, and what the state was before and after,
this table is the answer - not a description of the system's good
intentions.

Design rules, enforced by convention in every service that writes here
(see compliance.py, si_orchestrator.py, and the API routes that call
record_audit_event):
  - Entries are NEVER updated or deleted. Only ever inserted.
  - Every entry records a real human actor (user_id) - never "system" or
    "autonomous" as the actor for a consequential change, because every
    consequential change in this platform requires a human action to
    trigger it in the first place.
  - before_state and after_state are stored as plain text snapshots,
    not interpretations - so the record reflects what was true, not
    what the system concluded about it.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)

    actor_user_id = Column(String, nullable=False, index=True)  # who did this - always a real user
    actor_role = Column(String, nullable=True)                   # their role at the time of the action

    entity_type = Column(String, nullable=False, index=True)     # e.g. "jurisdiction_node", "asset", "listing", "inspection"
    entity_id = Column(String, nullable=False, index=True)

    action = Column(String, nullable=False)                      # e.g. "status_changed", "reviewed", "disclosed", "check_failed"
    before_state = Column(Text, nullable=True)                   # plain snapshot, not an interpretation
    after_state = Column(Text, nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<AuditLog {self.entity_type}:{self.entity_id} {self.action} by {self.actor_user_id} at {self.created_at}>"
