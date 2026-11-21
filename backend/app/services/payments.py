"""
First Hawaiian Bank receive-only payment service.

GROUND TRUTH RULE: A transaction is only ever marked FEE_COLLECTED after
First Hawaiian Bank itself confirms, through a signature-verified credit
notification, that the exact platform fee arrived. Nothing in this file marks
a transaction as paid because a listing exists, a payment instruction was
merely issued, or any other non-bank-confirmed signal.

RECEIVE-ONLY: This module has no payout, transfer, withdrawal or
disbursement function. The platform never pays anyone.

NOTE ON THE NOTIFICATION FORMAT: The signature scheme below (HMAC-SHA256 of
the raw request body, hex encoded, optionally prefixed "sha256=") and the
JSON field names in InboundCreditEvent are a reasonable default, not a
confirmed First Hawaiian Bank specification. Before real money flows, obtain
the bank's actual incoming-credit notification specification and adjust
`verify_signature` and `InboundCreditEvent` to match it exactly.

This file contains no hardcoded revenue numbers, mock success responses or
simulated bank notifications. Without a configured webhook secret, incoming
notifications are rejected rather than trusted.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import memory_lock, money
from app.models.enums import BankEventStatus, TransactionStatus
from app.models.ledger import BankEvent, LedgerEntry, SettlementDestination
from app.models.transaction import Transaction

settings = get_settings()


class PaymentError(Exception):
    """Raised for anything that should be rejected loudly, never swallowed."""


class SignatureError(PaymentError):
    """The bank notification's signature was missing or did not verify."""


class InboundCreditEvent(BaseModel):
    """Receive-only bank credit notification. Adapt the field names to the
    bank's issued specification."""
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str
    payment_reference: str = Field(min_length=1, max_length=128)
    bank_reference: Optional[str] = Field(default=None, max_length=128)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    amount_minor: int = Field(gt=0)


# --------------------------------------------------------------------------
# Settlement destination
# --------------------------------------------------------------------------

def get_destination(db: Session) -> SettlementDestination:
    """Return the active settlement destination, creating it from the
    environment settings the first time it is needed."""
    dest = db.get(SettlementDestination, 1)
    if dest is None:
        dest = SettlementDestination(
            id=1,
            bank_name=settings.fhb_bank_name,
            branch=settings.fhb_branch,
            routing_number=settings.fhb_routing_number,
            account_number=settings.fhb_account_number or None,
        )
        db.add(dest)
        db.commit()
        db.refresh(dest)
    return dest


# --------------------------------------------------------------------------
# Payment instruction (what the payer is told to do)
# --------------------------------------------------------------------------

def _new_payment_reference() -> str:
    return "PRA-" + secrets.token_hex(5).upper()


def create_payment_instruction(db: Session, transaction: Transaction) -> dict:
    """Assign a unique payment reference to the transaction and return the
    instructions the payer needs. Raises if the account number has not been
    configured - the platform never guesses where money should go."""
    dest = get_destination(db)
    if not dest.account_number:
        raise PaymentError(
            "Settlement destination is not configured: set FHB_ACCOUNT_NUMBER "
            "or have an admin set it before issuing payment instructions."
        )

    if not transaction.payment_reference:
        for _ in range(5):
            candidate = _new_payment_reference()
            exists = (
                db.query(Transaction.id)
                .filter(Transaction.payment_reference == candidate)
                .first()
            )
            if not exists:
                transaction.payment_reference = candidate
                break
        else:
            raise PaymentError("Could not generate a unique payment reference.")
        db.commit()

    return {
        "transaction_id": transaction.id,
        "amount_due_minor": transaction.platform_fee_minor,
        "amount_due": money.format_minor(transaction.platform_fee_minor),
        "currency": transaction.currency,
        "pay_to": {
            "bank_name": dest.bank_name,
            "branch": dest.branch,
            "routing_number": dest.routing_number,
            "account_number": dest.account_number,
        },
        "payment_reference": transaction.payment_reference,
        "instructions": (
            "Send exactly the amount due and include the payment reference "
            "so the credit can be matched. Revenue is recorded only after "
            "First Hawaiian Bank confirms the credit."
        ),
    }


# --------------------------------------------------------------------------
# Incoming credit notifications
# --------------------------------------------------------------------------

def verify_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    secret = settings.fhb_webhook_secret
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    supplied = signature.strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied[len("sha256="):]
    return hmac.compare_digest(expected, supplied.strip().lower())


def _post_entries(db, event_id, transaction_id, entity_code, currency, amount_minor, credit_account):
    db.add_all([
        LedgerEntry(
            event_id=event_id, transaction_id=transaction_id, entity_code=entity_code,
            account_code="BANK_CASH", currency=currency,
            debit_minor=amount_minor, credit_minor=0,
        ),
        LedgerEntry(
            event_id=event_id, transaction_id=transaction_id, entity_code=entity_code,
            account_code=credit_account, currency=currency,
            debit_minor=0, credit_minor=amount_minor,
        ),
    ])


def handle_bank_credit(db: Session, raw_body: bytes, signature: Optional[str]) -> dict:
    """Verify and process one incoming credit notification. Safe to call
    repeatedly with the same event: duplicates return the original result
    and never double-count."""
    if not verify_signature(raw_body, signature):
        raise SignatureError("Invalid or missing bank signature.")

    try:
        event = InboundCreditEvent(**json.loads(raw_body))
    except (ValueError, ValidationError) as exc:
        raise PaymentError(f"Malformed bank notification: {exc}") from exc

    if event.event_type != "credit.received":
        return {"status": "ignored", "event_type": event.event_type}

    already = db.get(BankEvent, event.event_id)
    if already:
        return {"status": "duplicate", "event_id": event.event_id, "result": already.status.value}

    txn = (
        db.query(Transaction)
        .filter(Transaction.payment_reference == event.payment_reference)
        .first()
    )

    if txn is None:
        status = BankEventStatus.UNMATCHED
        entity = "UNASSIGNED"
        credit_account = "UNAPPLIED_RECEIPTS"
    else:
        entity = txn.entity_code
        fee_minor = txn.platform_fee_minor
        exact = (
            event.currency == txn.currency
            and event.amount_minor == fee_minor
            and txn.status == TransactionStatus.PENDING
        )
        status = BankEventStatus.APPLIED if exact else BankEventStatus.NEEDS_REVIEW
        credit_account = "REVENUE" if exact else "UNAPPLIED_RECEIPTS"

    try:
        db.add(BankEvent(
            event_id=event.event_id,
            status=status,
            payment_reference=event.payment_reference,
            bank_reference=event.bank_reference,
            currency=event.currency,
            amount_minor=event.amount_minor,
            transaction_id=txn.id if txn else None,
        ))
        db.flush()  # the primary key rejects a concurrent duplicate here
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate", "event_id": event.event_id}

    _post_entries(
        db, event.event_id, txn.id if txn else None, entity,
        event.currency, event.amount_minor, credit_account,
    )

    memory_lock.capture(
        db,
        memory_lock.EventType.SETTLEMENT_STATUS_CHANGED,
        {
            "bank_event_id": event.event_id,
            "result": status.value,
            "currency": event.currency,
            "amount_minor": event.amount_minor,
            "payment_reference": event.payment_reference,
            "transaction_id": txn.id if txn else None,
        },
        metadata={"bank_reference": event.bank_reference},
    )

    if txn is not None:
        previous_status = txn.status.value
        txn.bank_reference = event.bank_reference
        txn.received_at = datetime.utcnow()
        txn.status = (
            TransactionStatus.FEE_COLLECTED
            if status == BankEventStatus.APPLIED
            else TransactionStatus.NEEDS_REVIEW
        )
        memory_lock.capture(
            db,
            memory_lock.EventType.PAYMENT_STATUS_CHANGED,
            {
                "transaction_id": txn.id,
                "from_status": previous_status,
                "to_status": txn.status.value,
                "currency": txn.currency,
                "fee_minor": txn.platform_fee_minor,
                "credited_minor": event.amount_minor,
            },
            auction_id=txn.listing_id,
        )

    db.commit()
    return {"status": status.value, "event_id": event.event_id, "transaction_id": txn.id if txn else None}
