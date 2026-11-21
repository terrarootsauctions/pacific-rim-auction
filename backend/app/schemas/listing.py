from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import InspectionStatus, InspectionType, ListingType


class ListingCreate(BaseModel):
    asset_id: str
    listing_type: ListingType
    title: str
    description: Optional[str] = None
    # Exact decimal dollars, at most two places (e.g. "250000.00").
    asking_price_usd: Optional[Decimal] = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    platform_fee_rate: Decimal = Field(default=Decimal("0.03"), ge=0, le=1)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class ListingOut(BaseModel):
    id: str
    asset_id: str
    seller_id: Optional[str]
    listing_type: ListingType
    title: str
    description: Optional[str]
    currency: str
    asking_price_minor: Optional[int]
    current_bid_minor: Optional[int]
    platform_fee_rate_bps: int
    auction_sequence: int
    closed_at: Optional[datetime]
    compliance_hold: bool
    is_live: bool
    requires_inspection: bool
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class InspectionCreate(BaseModel):
    listing_id: str
    inspection_type: InspectionType
    inspector_name: Optional[str] = None
    inspector_license_number: Optional[str] = None


class InspectionUpdate(BaseModel):
    status: InspectionStatus
    report_summary: Optional[str] = None
    report_document_url: Optional[str] = None


class InspectionOut(BaseModel):
    id: str
    listing_id: str
    inspection_type: InspectionType
    status: InspectionStatus
    inspector_name: Optional[str]
    inspector_license_number: Optional[str]
    report_summary: Optional[str]
    report_document_url: Optional[str]
    completed_at: Optional[datetime]
    disclosed_at: Optional[datetime]

    model_config = {"from_attributes": True}
