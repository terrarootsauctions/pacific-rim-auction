from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.services.claim_intake import IntakeStatus, Relationship


class ClaimIntakeCreate(BaseModel):
    claimant_name: str
    contact_email: str
    country: str
    relationship: Relationship
    region: Optional[str] = None
    description: Optional[str] = None
    asset_id: Optional[str] = None


class ClaimIntakeOut(BaseModel):
    id: str
    asset_id: Optional[str]
    claimant_name: str
    contact_email: str
    relationship: Relationship
    country: str
    region: Optional[str]
    description: Optional[str]
    status: IntakeStatus
    legal_fee_cap_bps: Optional[int]
    agreed_fee_bps: Optional[int]
    authorization_document_sha256: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ClaimStatusUpdate(BaseModel):
    status: IntakeStatus


class ClaimFeeSet(BaseModel):
    legal_fee_cap_bps: Optional[int] = None
    agreed_fee_bps: Optional[int] = None
