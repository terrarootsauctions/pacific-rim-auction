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
from app.services import money, follow_the_sun, outreach, payments, resilience


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
        db.query(func.coalesce(func.sum(Transaction.platform_fee_minor), 0))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    confirmed_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status == TransactionStatus.FEE_COLLECTED)
        .scalar()
    )
    return {
        "currency": "USD",
        "confirmed_platform_fee_revenue_minor": int(confirmed_fee_total),
        "confirmed_platform_fee_revenue": money.format_minor(int(confirmed_fee_total)),
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


# ---------------------------------------------------------------------------
# Capability registry, briefings, metrics, reconciliation (read-only)
# ---------------------------------------------------------------------------
import hashlib
from pathlib import Path

from app.models.enums import BankEventStatus
from app.models.ledger import BankEvent, LedgerEntry
from app.models.memory import MemoryArchive, MemoryRecord, MemoryVerification


def capabilities(db: Session) -> list:
    """Honest status of every capability. A capability is only 'active' when the
    code is present AND the thing it depends on is actually in place."""
    from app.core.config import get_settings
    from app.services import onetrust

    s = get_settings()
    last_ver = db.query(MemoryVerification).order_by(MemoryVerification.id.desc()).first() \
        if hasattr(MemoryVerification, "id") else None
    archived = db.query(func.count(MemoryArchive.id)).scalar() if hasattr(MemoryArchive, "id") else 0
    bank = _check_bank()
    return [
        {"name": "Live bid engine (atomic, idempotent, anti-sniping)", "status": "built",
         "detail": "Runs in this service; proven by unit tests of the rules, not yet by a live auction."},
        {"name": "Crystal Quartz Memory Lock (hash chain, Ed25519 + ML-DSA-65)", "status": "built",
         "detail": "Last verification: " + (last_ver.status if last_ver else "none yet")},
        {"name": "Physical quartz archive (5D glass/crystal)", "status": "requires_provider",
         "detail": f"No physical archiving is done here. Archive confirmations recorded: {archived}. "
                   "A record is only 'archived' after a provider confirms the matching package hash."},
        {"name": "First Hawaiian Bank receive rail", "status": bank["status"], "detail": bank["detail"]},
        {"name": "OneTrust compliance checkpoint", **onetrust.status()},
        {"name": "Follow the Sun scheduling", "status": "built",
         "detail": "Counts only legally reviewed (ACTIVE) jurisdictions."},
        {"name": "Autonomous algorithm evolution", "status": "built_bounded",
         "detail": "Applies only approved, bounded parameter changes with evidence and auto-revert. "
                   "It does not generate its own proposals; that needs real telemetry."},
        {"name": "Quantum computing", "status": "not_applicable",
         "detail": "No role in an auction platform. The quantum-era protection is the post-quantum signature."},
        {"name": "Hardware-hardened devices (seL4/Knox)", "status": "not_buildable_in_software",
         "detail": "Hardware/OS matter, outside this codebase."},
        {"name": "Background loop (auction close, hourly verification)", "status":
         "enabled" if s.background_enabled else "disabled", "detail": "Runs inside the web service."},
    ]


def tomorrow_prep(db: Session, hours: int = 24) -> dict:
    now = datetime.utcnow()
    closing = (
        db.query(Listing).filter(Listing.closed_at.is_(None), Listing.ends_at.isnot(None),
                                 Listing.ends_at <= now + timedelta(hours=hours)).all()
    )
    attention = db.query(BankEvent).filter(
        BankEvent.status.in_([BankEventStatus.NEEDS_REVIEW, BankEventStatus.UNMATCHED])).count()
    return {
        "generated_at": now.isoformat(),
        "auctions_closing_within_hours": hours,
        "closing_auctions": [{"listing_id": l.id, "closes_at": l.ends_at.isoformat(),
                              "current_bid_minor": l.current_bid_minor} for l in closing],
        "pending_inspections": pending_inspection_report(db),
        "jurisdictions_pending_review": jurisdiction_node_coverage(db)["pending_review"],
        "bank_events_needing_attention": attention,
    }


def reconciliation(db: Session) -> dict:
    """Ledger must balance (debits == credits) and every bank-confirmed fee must
    equal recorded revenue. Anything else is reported, never auto-corrected."""
    debit = db.query(func.coalesce(func.sum(LedgerEntry.debit_minor), 0)).scalar()
    credit = db.query(func.coalesce(func.sum(LedgerEntry.credit_minor), 0)).scalar()
    revenue = db.query(func.coalesce(func.sum(LedgerEntry.credit_minor), 0)).filter(
        LedgerEntry.account_code == "REVENUE").scalar()
    confirmed = real_revenue_summary(db)["confirmed_platform_fee_revenue_minor"]
    problems = []
    if int(debit) != int(credit):
        problems.append("LEDGER_UNBALANCED")
    if int(revenue) != int(confirmed):
        problems.append("REVENUE_MISMATCH")
    return {"status": "RECONCILED" if not problems else "DISCREPANCY", "problems": problems,
            "debits_minor": int(debit), "credits_minor": int(credit),
            "ledger_revenue_minor": int(revenue), "confirmed_fee_minor": int(confirmed)}


def build_manifest() -> dict:
    root = Path(__file__).resolve().parents[1]
    files = {}
    for p in sorted(root.rglob("*.py")):
        files[str(p.relative_to(root.parent))] = hashlib.sha256(p.read_bytes()).hexdigest()
    digest = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in files.items()).encode()).hexdigest()
    return {"files": len(files), "manifest_sha256": digest, "hashes": files}


def metrics_text(db: Session) -> str:
    rec = reconciliation(db)
    lines = [
        f"pacific_rim_memory_records {db.query(func.count(MemoryRecord.sequence)).scalar()}",
        f"pacific_rim_assets {db.query(func.count(Asset.id)).scalar()}",
        f"pacific_rim_listings {db.query(func.count(Listing.id)).scalar()}",
        f"pacific_rim_confirmed_revenue_minor {rec['confirmed_fee_minor']}",
        f"pacific_rim_reconciled {1 if rec['status'] == 'RECONCILED' else 0}",
    ]
    return "\n".join(lines) + "\n"
