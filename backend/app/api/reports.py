"""
Reporting API: SQL aggregation done in the database (GROUP BY, COUNT, SUM),
not in Python. Admin and compliance officers only.

  GET /reports/assets-by-category   count and total estimated USD value per category and status
  GET /reports/assets-by-country    count and total estimated USD value per source country
  GET /reports/claims-by-status     claim intakes per status and country
  GET /reports/commission           closed sales, gross sales and platform commission per currency

Money is stored in minor units (cents). Commission = winning bid x the
listing's own fee rate in basis points / 10,000, summed per currency.
Currencies are never added together.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.claim_intake import ClaimIntake
from app.models.enums import UserRole
from app.models.listing import Listing
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
