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
from app.services.fees import calculate_platform_fee

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
    if not listing.is_live:
        raise HTTPException(status_code=400, detail="Listing is not live")

    # Fail before creating anything if the bank destination is not set up.
    if not payments.get_destination(db).account_number:
        raise HTTPException(status_code=503, detail="Settlement destination is not configured yet.")

    fee = calculate_platform_fee(checkout_in.sale_amount_usd, listing.platform_fee_rate)

    transaction = Transaction(
        listing_id=listing.id,
        buyer_id=current_user.id,
        seller_id=listing.seller_id,
        entity_code="PRA_LLC",
        sale_amount_usd=checkout_in.sale_amount_usd,
        platform_fee_rate=listing.platform_fee_rate,
        platform_fee_usd=fee,
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
