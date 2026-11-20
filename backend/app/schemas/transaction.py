from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import TransactionStatus


class TransactionOut(BaseModel):
    id: str
    listing_id: str
    buyer_id: str
    seller_id: Optional[str]
    entity_code: str
    sale_amount_usd: float
    platform_fee_rate: float
    platform_fee_usd: float
    status: TransactionStatus
    payment_reference: Optional[str]
    bank_reference: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CheckoutCreate(BaseModel):
    listing_id: str
    sale_amount_usd: float = Field(gt=0)


class PaymentInstructionOut(BaseModel):
    transaction_id: str
    amount_due_usd: float
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
