from datetime import datetime

from pydantic import BaseModel


class BidCreate(BaseModel):
    listing_id: str
    amount_usd: float


class BidOut(BaseModel):
    id: str
    listing_id: str
    bidder_id: str
    amount_usd: float
    placed_at: datetime

    model_config = {"from_attributes": True}
