from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import TransactionStatus


class TransactionOut(BaseModel):
    id: str
    listing_id: str
    buyer_id: str
    seller_id: Optional[str]
    entity_code: str
    currency: str
    sale_amount_minor: int
    platform_fee_rate_bps: int
    platform_fee_minor: int
    status: TransactionStatus
    payment_reference: Optional[str]
    bank_reference: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CheckoutCreate(BaseModel):
    listing_id: str
    # Dollars as an exact decimal with at most two places, e.g. "250000.00".
    sale_amount_usd: Decimal = Field(gt=0, max_digits=15, decimal_places=2)


class PaymentInstructionOut(BaseModel):
    transaction_id: str
    amount_due_minor: int
    amount_due: str  # fixed two-decimal string, e.g. "7500.00"
    currency: str
    pay_to: dict
    payment_reference: str
    instructions: str


class SettlementDestinationOut(BaseModel):
    bank_name: str
    branch: str
    routing_number: str
    account_number: Optional[str]
    updated_by: Optional[str]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SettlementDestinationUpdate(BaseModel):
    """Changing where money is sent requires the admin's password again and
    the exact confirmation phrase, so it can never happen by accident or by
    an automated script."""
    routing_number: str = Field(min_length=9, max_length=9, pattern=r"^[0-9]{9}$")
    account_number: str = Field(min_length=4, max_length=34, pattern=r"^[0-9A-Za-z-]+$")
    password: str
    confirmation: str  # must equal "CHANGE SETTLEMENT DESTINATION"
