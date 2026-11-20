"""
Bank-side records: processed bank events (so no credit is ever counted
twice), a double-entry ledger, and the settlement destination.

Everything here is receive-only. There is no debit-to-payee, payout or
transfer record because the platform never pays anyone.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import BankEventStatus


def gen_uuid() -> str:
    return str(uuid.uuid4())


class BankEvent(Base):
    """One row per bank notification ever received. The primary key is the
    bank's event id, so a replayed or duplicated notification cannot be
    processed twice."""
    __tablename__ = "bank_events"

    event_id = Column(String, primary_key=True)
    status = Column(Enum(BankEventStatus), nullable=False)
    payment_reference = Column(String, nullable=True, index=True)
    bank_reference = Column(String, nullable=True)
    currency = Column(String(3), nullable=False)
    amount_minor = Column(Integer, nullable=False)  # e.g. cents
    transaction_id = Column(String, ForeignKey("transactions.id"), nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)


class LedgerEntry(Base):
    """Double-entry journal. Every confirmed credit writes a balanced pair:
    a debit to BANK_CASH and a credit to REVENUE (exact fee match) or to
    UNAPPLIED_RECEIPTS (cash arrived but could not be applied as revenue)."""
    __tablename__ = "ledger_entries"
    __table_args__ = (Index("ix_ledger_entity_account", "entity_code", "account_code"),)

    id = Column(String, primary_key=True, default=gen_uuid)
    event_id = Column(String, ForeignKey("bank_events.event_id"), nullable=False, index=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), nullable=True)
    entity_code = Column(String, nullable=False)
    account_code = Column(String, nullable=False)  # BANK_CASH | REVENUE | UNAPPLIED_RECEIPTS
    currency = Column(String(3), nullable=False)
    debit_minor = Column(Integer, nullable=False, default=0)
    credit_minor = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class SettlementDestination(Base):
    """The single bank destination that payers are told to send money to.
    Only an admin can change it, with password re-entry and a typed
    confirmation, and every change is written to the permanent audit log."""
    __tablename__ = "settlement_destination"

    id = Column(Integer, primary_key=True)  # always 1 - there is one active destination
    bank_name = Column(String, nullable=False)
    branch = Column(String, nullable=False)
    routing_number = Column(String, nullable=False)
    account_number = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)  # user id of the admin who last changed it
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
