from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import verify_password
from app.models.enums import BankEventStatus, TransactionStatus, UserRole
from app.models.ledger import BankEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import SettlementDestinationOut, SettlementDestinationUpdate
from app.services import payments
from app.services.audit import record_audit_event

router = APIRouter(prefix="/admin", tags=["admin"])

CONFIRMATION_PHRASE = "CHANGE SETTLEMENT DESTINATION"


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/revenue")
def get_real_revenue(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """The ONLY revenue figure this platform will ever report: the sum of
    platform_fee_usd across transactions whose exact fee credit First
    Hawaiian Bank has confirmed (status == FEE_COLLECTED). Until a real
    bank-confirmed credit exists, this returns zero - by design, not as a
    placeholder."""
    confirmed_fee_total = (
        db.query(func.coalesce(func.sum(Transaction.platform_fee_usd), 0.0))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    confirmed_sale_total = (
        db.query(func.coalesce(func.sum(Transaction.sale_amount_usd), 0.0))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    confirmed_transaction_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )

    return {
        "source_of_truth": "First Hawaiian Bank-confirmed credits only (status=FEE_COLLECTED)",
        "confirmed_platform_fee_revenue_usd": confirmed_fee_total,
        "confirmed_gross_sale_volume_usd": confirmed_sale_total,
        "confirmed_transaction_count": confirmed_transaction_count,
    }


@router.get("/bank-events/attention")
def bank_events_needing_attention(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Bank credits that arrived but could NOT be counted as revenue: no
    matching payment reference, or an amount/currency that did not match
    the fee owed. The cash is recorded, but only a human resolves these."""
    rows = (
        db.query(BankEvent)
        .filter(BankEvent.status.in_([BankEventStatus.UNMATCHED, BankEventStatus.NEEDS_REVIEW]))
        .order_by(BankEvent.received_at.desc())
        .all()
    )
    return [
        {
            "event_id": r.event_id,
            "status": r.status.value,
            "payment_reference": r.payment_reference,
            "bank_reference": r.bank_reference,
            "currency": r.currency,
            "amount_minor": r.amount_minor,
            "transaction_id": r.transaction_id,
            "received_at": r.received_at.isoformat() if r.received_at else None,
        }
        for r in rows
    ]


@router.get("/settlement-destination", response_model=SettlementDestinationOut)
def get_settlement_destination(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return payments.get_destination(db)


@router.put("/settlement-destination", response_model=SettlementDestinationOut)
def update_settlement_destination(
    update: SettlementDestinationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Change where payers are told to send money. This is the one setting
    that controls where revenue lands, so it requires the admin's password
    again plus the exact confirmation phrase, and every change is written
    to the permanent audit log with the before and after values."""
    if update.confirmation != CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'Type the confirmation phrase exactly: "{CONFIRMATION_PHRASE}"',
        )
    if not verify_password(update.password, admin.hashed_password):
        raise HTTPException(status_code=403, detail="Password did not match.")

    dest = payments.get_destination(db)
    before = f"routing={dest.routing_number}; account=...{(dest.account_number or '')[-4:]}"

    dest.routing_number = update.routing_number
    dest.account_number = update.account_number
    dest.updated_by = admin.id
    dest.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(dest)

    after = f"routing={dest.routing_number}; account=...{dest.account_number[-4:]}"
    record_audit_event(
        db,
        actor_user_id=admin.id,
        actor_role=admin.role.value,
        entity_type="settlement_destination",
        entity_id="1",
        action="destination_changed",
        before_state=before,
        after_state=after,
        notes="Settlement destination changed by admin with password re-entry and typed confirmation.",
    )
    return dest
