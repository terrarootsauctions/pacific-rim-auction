from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import AssetCategory, AssetStatus


class AssetCreate(BaseModel):
    category: AssetCategory
    title: str
    description: Optional[str] = None
    source_country: str
    source_region: Optional[str] = None
    dormant_since_year: Optional[int] = None
    years_dormant: Optional[int] = None
    estimated_value_usd: Optional[float] = None
    provenance_notes: Optional[str] = None


class AssetOut(BaseModel):
    id: str
    category: AssetCategory
    status: AssetStatus
    title: str
    description: Optional[str]
    source_country: str
    source_region: Optional[str]
    dormant_since_year: Optional[int]
    years_dormant: Optional[int]
    estimated_value_usd: Optional[float]
    do_no_harm_cleared: str
    jurisdiction_cleared: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetStatusUpdate(BaseModel):
    status: AssetStatus
