from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import verify_password
from app.models.enums import BankEventStatus, TransactionStatus, UserRole
from app.core.config import get_settings
from app.models.ledger import BankEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import SettlementDestinationOut, SettlementDestinationUpdate
from app.models.listing import Listing
from app.services import evolution, memory_lock, money, onetrust, payments
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
    platform_fee_minor (whole cents) across transactions whose exact fee credit First
    Hawaiian Bank has confirmed (status == FEE_COLLECTED). Until a real
    bank-confirmed credit exists, this returns zero - by design, not as a
    placeholder."""
    confirmed_fee_total = (
        db.query(func.coalesce(func.sum(Transaction.platform_fee_minor), 0))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    confirmed_sale_total = (
        db.query(func.coalesce(func.sum(Transaction.sale_amount_minor), 0))
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
        "currency": "USD",
        "confirmed_platform_fee_revenue_minor": int(confirmed_fee_total),
        "confirmed_platform_fee_revenue": money.format_minor(int(confirmed_fee_total)),
        "confirmed_gross_sale_volume_minor": int(confirmed_sale_total),
        "confirmed_gross_sale_volume": money.format_minor(int(confirmed_sale_total)),
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
    memory_lock.capture(
        db, memory_lock.EventType.ADMINISTRATIVE_ACTION,
        {"action": "settlement_destination_changed", "entity": "settlement_destination",
         "account_last4_after": (update.account_number or "")[-4:]},
        actor_id=admin.id,
    )
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


@router.get("/bank-rail/status")
def bank_rail_status(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Is the First Hawaiian Bank rail actually connected? 'Connected' is
    proven only one way: a real, signature-verified credit from the bank has
    been matched and applied. Settings alone never count as proof."""
    settings = get_settings()
    dest = payments.get_destination(db)

    checks = {
        "webhook_secret_set": bool(settings.fhb_webhook_secret),
        "account_number_set": bool(dest.account_number),
        "routing_number_valid": bool(dest.routing_number)
        and len(dest.routing_number) == 9
        and dest.routing_number.isdigit(),
    }
    applied_count = (
        db.query(func.count(BankEvent.event_id))
        .filter(BankEvent.status == BankEventStatus.APPLIED)
        .scalar()
    )
    last_event_at = db.query(func.max(BankEvent.received_at)).scalar()

    if not all(checks.values()):
        state = "not_configured"
        next_step = "Set the missing items shown as false in 'checks' (on the host, not in GitHub)."
    elif applied_count == 0:
        state = "configured_awaiting_first_credit"
        next_step = (
            "Settings are in place. Run one small real test: issue a payment "
            "instruction, send that exact amount with the reference, and wait "
            "for First Hawaiian Bank's signed notification."
        )
    else:
        state = "proven"
        next_step = "A real bank credit has been received and applied. The rail is working."

    return {
        "state": state,
        "checks": checks,
        "applied_bank_credits": applied_count,
        "last_bank_event_at": last_event_at.isoformat() if last_event_at else None,
        "next_step": next_step,
    }


# --------------------------------------------------------------------------
# Compliance hold: never guess legality. A held auction stops accepting bids.
# --------------------------------------------------------------------------
from pydantic import BaseModel, Field  # noqa: E402


class ComplianceHoldRequest(BaseModel):
    hold: bool
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/listings/{listing_id}/compliance-hold")
def set_compliance_hold(
    listing_id: str,
    body: ComplianceHoldRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    before = f"compliance_hold={listing.compliance_hold}"
    listing.compliance_hold = body.hold
    listing.compliance_hold_reason = body.reason if body.hold else None
    db.commit()
    record_audit_event(
        db,
        actor_user_id=admin.id,
        actor_role=admin.role.value,
        entity_type="listing",
        entity_id=listing.id,
        action="compliance_hold_set" if body.hold else "compliance_hold_lifted",
        before_state=before,
        after_state=f"compliance_hold={listing.compliance_hold}",
        notes=body.reason,
    )
    return {"listing_id": listing.id, "compliance_hold": listing.compliance_hold}


# --------------------------------------------------------------------------
# Autonomous Algorithm Evolution: bounded, evidence-gated, fully recorded.
# --------------------------------------------------------------------------
class ParameterChange(BaseModel):
    parameter: str
    new_value: int
    reason: str = Field(min_length=3, max_length=2000)
    evidence: dict


class RollbackRequest(BaseModel):
    parameter: str
    reason: str = Field(min_length=3, max_length=2000)


class MetricsReport(BaseModel):
    parameter: str
    metrics: dict
    thresholds: dict


@router.get("/evolution/parameters")
def get_evolution_parameters(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from app.services import evolution_rules

    return {
        "current": evolution.get_params(db),
        "bounds": {k: {"min": v[0], "max": v[1]} for k, v in evolution_rules.PARAMETERS.items()},
        "protected_never_changeable": sorted(evolution_rules.PROTECTED),
    }


@router.post("/evolution/change")
def propose_parameter_change(body: ParameterChange, db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    return evolution.propose_change(db, body.parameter, body.new_value, body.reason,
                                    body.evidence, admin.id)


@router.post("/evolution/rollback")
def rollback_parameter(body: RollbackRequest, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    return evolution.rollback(db, body.parameter, body.reason, admin.id)


@router.post("/evolution/evaluate")
def evaluate_parameter(body: MetricsReport, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    """Report observed metrics after a change. If any predefined safety
    threshold is violated (or a metric is missing), the change is reverted."""
    return evolution.evaluate_and_revert(db, body.parameter, body.metrics, body.thresholds, admin.id)


@router.get("/onetrust/status")
def onetrust_status(admin: User = Depends(require_admin)):
    return onetrust.status()
