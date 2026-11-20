from typing import Optional

from pydantic import BaseModel, EmailStr

from app.services.outreach import OutreachCampaignType


class OutreachContactCreate(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    country: Optional[str] = None
    campaign_type: OutreachCampaignType
    campaign_id: str  # the real Reply.io campaign ID to enroll this contact into
