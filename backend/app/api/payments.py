from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.listing import Listing
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import CheckoutCreate, PaymentInstructionOut
from app.services import payments
from app.services import money
from app.services.fees import calculate_fee_minor_from_bps

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/checkout", response_model=PaymentInstructionOut, status_code=201)
def create_checkout(
    checkout_in: CheckoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Transaction and return bank payment instructions. The
    transaction starts PENDING and becomes FEE_COLLECTED only when First
    Hawaiian Bank confirms the credit through /payments/bank-webhook -
    never before."""
    listing = db.query(Listing).filter(Listing.id == checkout_in.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    # An auction that has closed is no longer "live" (closing switches that off), but its winner must still be
    # able to pay. For a closed auction only the winning bidder may check out, at the recorded winning bid; the
    # amount is never taken from the request. A listing still live (fixed price) is paid as before.
    closed_winner_sale_minor = None
    if listing.closed_at is not None and listing.winner_id:
        if current_user.id != listing.winner_id:
            raise HTTPException(status_code=403, detail="Only the winning bidder can pay for this listing")
        closed_winner_sale_minor = int(listing.winning_bid_minor)
    elif not listing.is_live:
        raise HTTPException(status_code=400, detail="Listing is not live")

    # Fail before creating anything if the bank destination is not set up.
    if not payments.get_destination(db).account_number:
        raise HTTPException(status_code=503, detail="Settlement destination is not configured yet.")

    sale_minor = closed_winner_sale_minor if closed_winner_sale_minor is not None else money.usd_to_minor(checkout_in.sale_amount_usd)
    fee_minor, rate_bps = calculate_fee_minor_from_bps(sale_minor, listing.platform_fee_rate_bps)

    transaction = Transaction(
        listing_id=listing.id,
        buyer_id=current_user.id,
        seller_id=listing.seller_id,
        entity_code="PRA_LLC",
        currency="USD",
        sale_amount_minor=sale_minor,
        platform_fee_rate_bps=rate_bps,
        platform_fee_minor=fee_minor,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    try:
        return payments.create_payment_instruction(db, transaction)
    except payments.PaymentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/transactions/{transaction_id}/instructions", response_model=PaymentInstructionOut)
def get_instructions(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if transaction.buyer_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not your transaction")
    try:
        return payments.create_payment_instruction(db, transaction)
    except payments.PaymentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/bank-webhook")
async def bank_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives First Hawaiian Bank credit notifications. Every request must
    carry a valid signature in the X-FHB-Signature header. Duplicate
    notifications are safe: each bank event id is processed once."""
    raw_body = await request.body()
    signature = request.headers.get("x-fhb-signature")
    try:
        return payments.handle_bank_credit(db, raw_body, signature)
    except payments.SignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except payments.PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


from pydantic import BaseModel as _BM  # noqa: E402
from app.services.audit import record_audit_event as _audit  # noqa: E402


class ManualCredit(_BM):
    payment_reference: str      # the PRA-... reference the payer used
    amount_usd: float
    bank_reference: str         # the reference on the bank statement line (makes this safe to repeat)
    currency: str = "USD"
    notes: str = ""


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/confirm-credit")
def confirm_credit(body: ManualCredit, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Record a credit you can see on the bank statement, without waiting for a bank notification. Same matching
    and ledger rules as the bank webhook: an exact fee match becomes revenue, anything else goes to review."""
    _require_admin(current_user)
    try:
        result = payments.confirm_credit_manually(
            db, payment_reference=body.payment_reference, amount_minor=money.usd_to_minor(body.amount_usd),
            currency=body.currency, bank_reference=body.bank_reference)
    except payments.PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(db, actor_user_id=current_user.id, actor_role=current_user.role.value, entity_type="bank_credit",
           entity_id=body.bank_reference, action="credit_confirmed_manually", before_state=None,
           after_state=str(result.get("status")), notes=body.notes or None)
    return result


@router.post("/transactions/{transaction_id}/resolve")
def resolve_transaction(transaction_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Admin: recognize a needs_review transaction as collected, only if the bank credits received for it cover the fee."""
    _require_admin(current_user)
    try:
        result = payments.resolve_needs_review(db, transaction_id)
    except payments.PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(db, actor_user_id=current_user.id, actor_role=current_user.role.value, entity_type="transaction",
           entity_id=transaction_id, action="needs_review_resolved", before_state="needs_review",
           after_state="fee_collected", notes=None)
    return result
