"""
SI (Synthetic Intelligence) - the platform orchestrator.

CORE PRINCIPLE: Donovan is the human in the loop. SI is the architect's
instrument, not a second decision-maker. SI's role is strictly limited to:

  1. Watching the platform's real, already-integrated systems (the First
     Hawaiian Bank receive rail, compliance screening, outreach, the
     database itself) and reporting their actual status.
  2. Surfacing recommendations - "this looks broken," "this hasn't been
     used in 90 days," "here's a new tool that might fit" - for the
     human architect to evaluate.
  3. NEVER autonomously adding, removing, or reconfiguring integrations,
     and NEVER approving or executing a transaction, listing, or payout
     on its own authority.

Every function in this file returns information. None of them take
action that can't be trivially undone by simply not reading the report.
This is intentional and should not be "improved" into something that
acts autonomously - that would reintroduce exactly the autonomous,
no-override risk already rejected for the payments and tooling layers
elsewhere in this platform.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import AssetStatus, InspectionStatus, TransactionStatus
from app.models.jurisdiction_node import JurisdictionNode, NodeStatus
from app.models.listing import Inspection, Listing
from app.models.transaction import Transaction
from app.services import follow_the_sun, outreach, payments, resilience


def system_health_report(db: Session) -> dict:
    """A single, honest snapshot of what's actually working right now.
    Every field here reflects a real check, not an assumption."""
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "bank": _check_bank(),
        "reply_io": _check_reply_io(),
        "database": _check_database(db),
        "circuit_breakers": resilience.all_snapshots(),
        "note": "This report reflects only the systems already integrated "
        "into the codebase. Nothing here is inferred or projected.",
    }
    return report


def _check_bank() -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    missing = []
    if not settings.fhb_webhook_secret:
        missing.append("FHB_WEBHOOK_SECRET")
    if not settings.fhb_account_number:
        missing.append("FHB_ACCOUNT_NUMBER (unless an admin has set the destination)")
    if missing:
        return {"status": "not_configured", "detail": "Not set: " + ", ".join(missing)}
    return {
        "status": "configured",
        "detail": "Bank settings present. A real credit notification from the bank is the only proof the rail works.",
    }


def _check_reply_io() -> dict:
    try:
        result = outreach.verify_credentials()
        return {"status": "connected", "detail": result}
    except RuntimeError as exc:
        return {"status": "not_configured", "detail": str(exc)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_database(db: Session) -> dict:
    try:
        asset_count = db.query(func.count(Asset.id)).scalar()
        listing_count = db.query(func.count(Listing.id)).scalar()
        return {"status": "connected", "assets": asset_count, "listings": listing_count}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def stalled_assets_report(db: Session, days: int = 14) -> List[dict]:
    """Surfaces assets that have sat in SOURCED or UNDER_REVIEW for longer
    than `days` with no status change - a recommendation for the architect
    to look at, not an automatic escalation or rejection."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stalled = (
        db.query(Asset)
        .filter(
            Asset.status.in_([AssetStatus.SOURCED, AssetStatus.UNDER_REVIEW]),
            Asset.updated_at < cutoff,
        )
        .all()
    )
    return [
        {
            "asset_id": a.id,
            "title": a.title,
            "category": a.category.value,
            "status": a.status.value,
            "days_stalled": (datetime.utcnow() - a.updated_at).days,
        }
        for a in stalled
    ]


def pending_inspection_report(db: Session) -> List[dict]:
    """Surfaces listings whose required inspections are incomplete or
    undisclosed - exactly the gate compliance.py enforces, but here for
    the architect's visibility rather than as a blocking check."""
    pending = (
        db.query(Inspection)
        .filter(Inspection.status != InspectionStatus.DISCLOSED)
        .all()
    )
    return [
        {
            "inspection_id": i.id,
            "listing_id": i.listing_id,
            "type": i.inspection_type.value,
            "status": i.status.value,
        }
        for i in pending
    ]


def real_revenue_summary(db: Session) -> dict:
    """The same bank-confirmed-only standard as admin.py's /revenue
    endpoint, surfaced here as part of SI's report so the architect sees
    it alongside everything else in one place."""
    confirmed_fee_total = (
        db.query(func.coalesce(func.sum(Transaction.platform_fee_usd), 0.0))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    confirmed_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    return {
        "confirmed_platform_fee_revenue_usd": confirmed_fee_total,
        "confirmed_transaction_count": confirmed_count,
        "source_of_truth": "First Hawaiian Bank-confirmed credits only",
    }


def failed_jurisdiction_checks_report(db: Session) -> list:
    """Surfaces every jurisdiction node with a recorded check failure -
    the permanent record the architect directed be kept, never deleted.
    This is exactly the visibility that record exists to provide."""
    failed = (
        db.query(JurisdictionNode)
        .filter(JurisdictionNode.status == NodeStatus.CHECK_FAILED)
        .all()
    )
    return [
        {
            "node_id": n.id,
            "country_code": n.country_code,
            "region_code": n.region_code,
            "failure_reason": n.last_check_failure_reason,
            "source": n.last_check_source,
            "failed_at": n.last_check_failed_at.isoformat() if n.last_check_failed_at else None,
        }
        for n in failed
    ]


def jurisdiction_node_coverage(db: Session) -> dict:
    """Surfaces how much of the 'follow the sun' jurisdiction structure
    is actually reviewed and active versus just structurally present.
    Built-ahead-of-need nodes still need real legal review before they
    can clear anything - this report shows the gap honestly."""
    total = db.query(func.count(JurisdictionNode.id)).scalar()
    active = (
        db.query(func.count(JurisdictionNode.id))
        .filter(JurisdictionNode.status == NodeStatus.ACTIVE)
        .scalar()
    )
    pending = (
        db.query(func.count(JurisdictionNode.id))
        .filter(JurisdictionNode.status == NodeStatus.PENDING_REVIEW)
        .scalar()
    )
    restricted = (
        db.query(func.count(JurisdictionNode.id))
        .filter(JurisdictionNode.status == NodeStatus.RESTRICTED)
        .scalar()
    )
    suspended = (
        db.query(func.count(JurisdictionNode.id))
        .filter(JurisdictionNode.status == NodeStatus.SUSPENDED)
        .scalar()
    )
    return {
        "total_nodes": total,
        "active": active,
        "pending_review": pending,
        "restricted": restricted,
        "suspended": suspended,
        "note": "A node existing does not mean it is cleared. Only ACTIVE "
        "nodes (real legal review completed) can clear a listing in that "
        "jurisdiction.",
    }


def full_architect_briefing(db: Session) -> dict:
    """The single report SI hands to the human architect. Nothing in
    here is auto-applied - it's a briefing, not an action log."""
    return {
        "system_health": system_health_report(db),
        "stalled_assets": stalled_assets_report(db),
        "pending_inspections": pending_inspection_report(db),
        "jurisdiction_coverage": jurisdiction_node_coverage(db),
        "follow_the_sun": follow_the_sun.follow_the_sun_report(db),
        "failed_jurisdiction_checks": failed_jurisdiction_checks_report(db),
        "revenue": real_revenue_summary(db),
        "reminder": "SI does not act on any of this. The architect decides.",
    }
