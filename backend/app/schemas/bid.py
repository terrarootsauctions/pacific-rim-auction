from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BidCreate(BaseModel):
    listing_id: str
    # Exact decimal dollars with at most two places, e.g. "1250.00".
    amount_usd: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    # Required. Repeating the same key never creates a second bid.
    idempotency_key: str = Field(min_length=8, max_length=128)
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")


class BidOut(BaseModel):
    id: str
    listing_id: str
    bidder_id: str
    currency: str
    amount_minor: int
    sequence: int
    placed_at: datetime

    model_config = {"from_attributes": True}


class BidResult(BaseModel):
    outcome: str            # "accepted" or "duplicate" (original result returned)
    bid: BidOut
    auction_sequence: int
    closes_at: datetime | None
    extended: bool
