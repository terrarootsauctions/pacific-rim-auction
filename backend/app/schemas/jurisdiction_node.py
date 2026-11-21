from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.jurisdiction_node import NodeStatus


class JurisdictionNodeOut(BaseModel):
    id: str
    country_code: str
    country_name: str
    region_code: Optional[str]
    region_name: Optional[str]
    status: NodeStatus
    disclosure_requirements: Optional[str]
    licensing_requirements: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class JurisdictionNodeReview(BaseModel):
    """Submitted by a human - the architect or a compliance attorney -
    to move a node from PENDING_REVIEW to ACTIVE/RESTRICTED/SUSPENDED.
    This is never set automatically."""
    status: NodeStatus
    disclosure_requirements: Optional[str] = None
    licensing_requirements: Optional[str] = None
    sanctions_notes: Optional[str] = None
    reviewed_by: str


class CheckFailureResolution(BaseModel):
    """Submitted by a human resolving a CHECK_FAILED node. If
    save_as_precedent is True, this exact resolution will be applied
    automatically to any future, identically-matched failure - per the
    architect's directive that SI should not re-ask about a case it has
    already faced and resolved."""
    new_status: NodeStatus
    resolution_notes: Optional[str] = None
    save_as_precedent: bool = True
