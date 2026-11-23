from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from app.models.enums import AssetCategory, AssetStatus
from app.services import dormancy


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

    @field_validator("dormant_since_year")
    @classmethod
    def _year_in_range(cls, v):
        return dormancy.validate_dormant_since_year(v)

    @model_validator(mode="after")
    def _calculate_years_dormant(self):
        # Calculated from the year, never typed in by hand.
        if self.dormant_since_year is not None:
            self.years_dormant = dormancy.years_dormant(self.dormant_since_year)
        return self


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

    @model_validator(mode="after")
    def _fresh_years_dormant(self):
        # Recalculated on every read, so stored values never go stale across years.
        if self.dormant_since_year is not None:
            self.years_dormant = dormancy.years_dormant(self.dormant_since_year)
        return self


class AssetStatusUpdate(BaseModel):
    status: AssetStatus
