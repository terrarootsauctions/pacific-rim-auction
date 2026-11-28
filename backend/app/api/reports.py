"""
Reporting API: SQL aggregation done in the database (GROUP BY, COUNT, SUM),
not in Python. Admin and compliance officers only.

  GET /reports/assets-by-category   count and total estimated USD value per category and status
  GET /reports/assets-by-country    count and total estimated USD value per source country
  GET /reports/assets-by-dormancy-decade   count and value by the decade the asset went dormant (1840s to now)
  GET /reports/claims-by-status     claim intakes per status and country
  GET /reports/commission           closed sales, gross sales and platform commission per currency
  GET /reports/revenue-pipeline     uncollected winners + where every unclaimed property sits on the way to a sale

Money is stored in minor units (cents). Commission = winning bid x the
listing's own fee rate in basis points / 10,000, summed per currency.
Currencies are never added together.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.claim_intake import ClaimIntake
from app.models.enums import AssetStatus, UserRole
from app.models.listing import Listing
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])


def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Admin or compliance officer access required")
    return current_user


def _name(value):
    return getattr(value, "value", value)


@router.get("/assets-by-category")
def assets_by_category(db: Session = Depends(get_db), _: User = Depends(require_reviewer)) -> List[dict]:
    rows = (
        db.query(
            Asset.category,
            Asset.status,
            func.count(Asset.id),
            func.coalesce(func.sum(Asset.estimated_value_usd), 0.0),
        )
        .group_by(Asset.category, Asset.status)
        .order_by(Asset.category, Asset.status)
        .all()
    )
    return [
        {"category": _name(c), "status": _name(s), "count": n, "estimated_value_usd": float(v)}
        for c, s, n, v in rows
    ]


@router.get("/assets-by-country")
def assets_by_country(db: Session = Depends(get_db), _: User = Depends(require_reviewer)) -> List[dict]:
    rows = (
        db.query(
            Asset.source_country,
            func.count(Asset.id),
            func.coalesce(func.sum(Asset.estimated_value_usd), 0.0),
        )
        .group_by(Asset.source_country)
        .order_by(func.count(Asset.id).desc(), Asset.source_country)
        .all()
    )
    return [{"country": c, "count": n, "estimated_value_usd": float(v)} for c, n, v in rows]


@router.get("/assets-by-dormancy-decade")
def assets_by_dormancy_decade(db: Session = Depends(get_db), _: User = Depends(require_reviewer)) -> List[dict]:
    decade = (Asset.dormant_since_year // 10) * 10
    rows = (
        db.query(decade, func.count(Asset.id), func.coalesce(func.sum(Asset.estimated_value_usd), 0.0))
        .filter(Asset.dormant_since_year.isnot(None))
        .group_by(decade)
        .order_by(decade)
        .all()
    )
    return [{"decade": int(d), "count": n, "estimated_value_usd": float(v)} for d, n, v in rows]


@router.get("/claims-by-status")
def claims_by_status(db: Session = Depends(get_db), _: User = Depends(require_reviewer)) -> List[dict]:
    rows = (
        db.query(ClaimIntake.status, ClaimIntake.country, func.count(ClaimIntake.id))
        .group_by(ClaimIntake.status, ClaimIntake.country)
        .order_by(ClaimIntake.status, ClaimIntake.country)
        .all()
    )
    return [{"status": _name(s), "country": c, "count": n} for s, c, n in rows]


@router.get("/commission")
def commission(db: Session = Depends(get_db), _: User = Depends(require_reviewer)) -> List[dict]:
    """Only closed listings with a winning bid count. Compliance-held
    listings are excluded."""
    rows = (
        db.query(
            Listing.currency,
            func.count(Listing.id),
            func.sum(Listing.winning_bid_minor),
            func.sum(Listing.winning_bid_minor * Listing.platform_fee_rate_bps / 10000),
        )
        .filter(Listing.closed_at.isnot(None))
        .filter(Listing.winning_bid_minor.isnot(None))
        .filter(Listing.compliance_hold.is_(False))
        .group_by(Listing.currency)
        .order_by(Listing.currency)
        .all()
    )
    return [
        {
            "currency": cur,
            "closed_sales": n,
            "gross_sales_minor": int(gross or 0),
            "commission_minor": int(comm or 0),
        }
        for cur, n, gross, comm in rows
    ]


@router.get("/revenue-pipeline")
def revenue_pipeline(db: Session = Depends(get_db), _: User = Depends(require_reviewer)) -> dict:
    """Where money is waiting. (1) Closed auctions with a winner, split by payment state: nothing started,
    started but not confirmed, or collected. (2) Every asset by stage on the way to a sale, with its estimated
    value and the fee it would earn at the standard rate. Estimates come from the records' own numbers."""
    # ---- (1) winners and what has been paid ----
    closed = (db.query(Listing).filter(Listing.closed_at.isnot(None), Listing.winning_bid_minor.isnot(None),
                                       Listing.compliance_hold.is_(False)).all())
    ids = [l.id for l in closed]
    tx_by_listing = {}
    if ids:
        for t in db.query(Transaction).filter(Transaction.listing_id.in_(ids)).all():
            tx_by_listing.setdefault(t.listing_id, []).append(t)
    buckets = {"no_payment_started": [], "payment_pending": [], "collected": []}
    for l in closed:
        txs = tx_by_listing.get(l.id, [])
        fee = int((l.winning_bid_minor or 0) * (l.platform_fee_rate_bps or 0) / 10000)
        row = {"listing_id": l.id, "winner_id": l.winner_id, "currency": l.currency,
               "winning_bid_minor": int(l.winning_bid_minor), "fee_minor": fee, "closed_at": l.closed_at.isoformat()}
        if any(t.status == TransactionStatus.FEE_COLLECTED for t in txs):
            buckets["collected"].append(row)
        elif txs:
            buckets["payment_pending"].append(row)
        else:
            buckets["no_payment_started"].append(row)

    def _tot(rows):
        out = {}
        for r in rows:
            c = out.setdefault(r["currency"], {"count": 0, "sales_minor": 0, "fees_minor": 0})
            c["count"] += 1
            c["sales_minor"] += r["winning_bid_minor"]
            c["fees_minor"] += r["fee_minor"]
        return out

    winners = {k: {"totals": _tot(v), "listings": v[:200]} for k, v in buckets.items()}

    # ---- (2) unclaimed property funnel ----
    has_listing = exists().where(Listing.asset_id == Asset.id)
    stages = {
        "not_yet_verified": (Asset.status.in_([AssetStatus.SOURCED, AssetStatus.UNDER_REVIEW]),),
        "verified_do_no_harm_pending": (Asset.status == AssetStatus.VERIFIED, Asset.do_no_harm_cleared == "pending"),
        "verified_do_no_harm_flagged": (Asset.status == AssetStatus.VERIFIED, Asset.do_no_harm_cleared == "flagged"),
        "verified_cleared_not_listed": (Asset.status == AssetStatus.VERIFIED, Asset.do_no_harm_cleared == "cleared", ~has_listing),
        "listed_or_in_sale": (Asset.status.in_([AssetStatus.LISTED, AssetStatus.UNDER_CONTRACT]),),
        "sold": (Asset.status == AssetStatus.SOLD,),
    }
    funnel = {}
    for name, conds in stages.items():
        n, v = db.query(func.count(Asset.id), func.sum(Asset.estimated_value_usd)).filter(*conds).one()
        value = float(v or 0)
        funnel[name] = {"assets": n, "estimated_value_usd": round(value, 2),
                        "estimated_fee_usd_at_standard_rate": round(value * 0.05, 2)}
    return {"winners": winners, "unclaimed_property_funnel": funnel,
            "notes": "Fee estimates use 5% on the records' own estimated values; they are not forecasts of what will close."}
