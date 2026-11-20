"""
JurisdictionNode model - the concrete data structure behind the platform's
"follow the sun, 2,500 nodes, 190 countries" architecture.

Each node represents one sub-national jurisdiction (country + region/state/
province) and carries that specific jurisdiction's compliance posture -
disclosure requirements, licensing requirements, and standing under the
platform's two governing mandates: "Do No Harm" and "Follow the Laws of
the Land."

This is built in full from day one per the architect's directive, so the
structure exists ahead of demand rather than being grown reactively.
Nodes start in PENDING_REVIEW status - the structure existing on day one
does not mean every jurisdiction's actual legal review is complete on day
one. An asset cannot be cleared for listing in a jurisdiction whose node
has not been reviewed and marked ACTIVE, regardless of how many node rows
exist in the table. This keeps "built ahead of need" from quietly becoming
"approved ahead of review."
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class NodeStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"   # node exists, legal review not yet done
    ACTIVE = "active"                    # reviewed and cleared - assets can list here
    RESTRICTED = "restricted"            # reviewed, but with specific limitations
    SUSPENDED = "suspended"              # was active, now paused (e.g. sanctions, legal change)
    CHECK_FAILED = "check_failed"        # a real compliance check was attempted and failed -
                                          # kept as a permanent record, never silently deleted.
                                          # Listings cannot proceed in this jurisdiction until
                                          # a human reviews the failure and re-checks.


class JurisdictionNode(Base):
    __tablename__ = "jurisdiction_nodes"

    id = Column(String, primary_key=True, default=gen_uuid)

    country_code = Column(String, nullable=False, index=True)   # ISO 3166-1 alpha-2, e.g. "US"
    country_name = Column(String, nullable=False)
    region_code = Column(String, nullable=True, index=True)      # e.g. "HI" for Hawaii
    region_name = Column(String, nullable=True)                  # e.g. "Hawaii"

    status = Column(Enum(NodeStatus), default=NodeStatus.PENDING_REVIEW, nullable=False, index=True)

    # What "laws of the land" actually means for this specific place.
    # Filled in during real legal review - blank by default, never
    # auto-populated with placeholder legal claims.
    disclosure_requirements = Column(Text, nullable=True)
    licensing_requirements = Column(Text, nullable=True)
    sanctions_notes = Column(Text, nullable=True)

    reviewed_by = Column(String, nullable=True)   # name/ID of the attorney or compliance officer
    reviewed_at = Column(DateTime, nullable=True)

    # Permanent record of the most recent failed check, if any. Never
    # cleared automatically - a human must review and re-check before
    # this is overwritten, per the architect's directive that failed
    # checks are kept as a traceable record, not silently discarded.
    last_check_failure_reason = Column(Text, nullable=True)
    last_check_failed_at = Column(DateTime, nullable=True)
    last_check_source = Column(String, nullable=True)  # e.g. "LexisNexis WorldCompliance", "Westlaw"

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        loc = f"{self.country_code}/{self.region_code}" if self.region_code else self.country_code
        return f"<JurisdictionNode {loc} status={self.status.value}>"
