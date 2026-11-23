"""
Publisher - the database layer around the listing gate, and the recheck
that runs every Follow the Sun pass.

evaluate_go_live(): every condition that must hold before a listing is live
(legal-review gate, Do No Harm, lawful basis, required inspections, OneTrust).

recheck_all(): goes through every listing that is not live yet, runs the
same checks, and takes live the ones that now qualify. Anything still
missing something is left alone and tried again next pass. Each go-live is
recorded in the audit log under the listing's own seller (the audit rule is
that a real person is always the actor), with a note that it was automatic.
One listing failing never stops the rest.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.claim_intake import ClaimIntake
from app.models.lawful_basis import LawfulBasis
from app.models.listing import Listing
from app.services import compliance, listing_gate, memory_lock, onetrust
from app.services.audit import record_audit_event
from app.services.claim_intake import IntakeStatus

log = logging.getLogger("pacific_rim.publisher")


def _candidates(db: Session, asset: Asset) -> List[Dict]:
    candidates: List[Dict] = []
    for row in db.query(LawfulBasis).filter(LawfulBasis.asset_id == asset.id).all():
        candidates.append({
            "basis": row.basis,
            "reference": row.reference,
            "seller_holds_title": row.seller_holds_title,
        })
    claims = (
        db.query(ClaimIntake)
        .filter(ClaimIntake.asset_id == asset.id, ClaimIntake.status == IntakeStatus.AUTHORIZED)
        .all()
    )
    for claim in claims:
        try:
            events = json.loads(claim.signing_events) if claim.signing_events else []
        except ValueError:
            events = []
        candidates.append({
            "basis": listing_gate.BASIS_OWNER_AUTHORIZATION,
            "signing_events": events,
            "document_sha256": claim.authorization_document_sha256,
        })
    return candidates


def evaluate_asset_gate(db: Session, asset: Asset) -> Tuple[bool, List[str], Optional[str]]:
    jurisdiction_ok, jurisdiction_reason = compliance.jurisdiction_node_cleared(
        db, asset.source_country, asset.source_region
    )
    ok, reasons, basis = listing_gate.check_any(
        jurisdiction_ok, asset.do_no_harm_cleared or "pending", _candidates(db, asset)
    )
    if not jurisdiction_ok:
        reasons = [jurisdiction_reason if r.startswith("Jurisdiction") else r for r in reasons]
    return ok, reasons, basis


def evaluate_go_live(db: Session, listing: Listing, now: Optional[datetime] = None) -> Tuple[bool, List[str]]:
    now = now or datetime.utcnow()
    reasons: List[str] = []

    if listing.compliance_hold:
        reasons.append(f"Listing is on compliance hold: {listing.compliance_hold_reason or 'no reason recorded'}")
    if listing.ends_at and listing.ends_at <= now:
        reasons.append("The listing's end time has already passed.")

    asset = db.query(Asset).filter(Asset.id == listing.asset_id).first()
    if not asset:
        return False, reasons + ["Asset not found."]

    ok, gate_reasons, _basis = evaluate_asset_gate(db, asset)
    if not ok:
        reasons.extend(gate_reasons)

    cleared, reason = compliance.listing_cleared_to_go_live(db, listing)
    if not cleared:
        reasons.append(reason)

    ot_ok, ot_reason = onetrust.check_listing(listing)
    if not ot_ok:
        reasons.append(ot_reason)

    return (not reasons), reasons


def recheck_all(db: Session, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.utcnow()
    summary = {"checked": 0, "published": [], "waiting": 0, "errors": 0, "no_seller": 0}
    pending = (
        db.query(Listing)
        .filter(Listing.is_live.is_(False), Listing.closed_at.is_(None), Listing.compliance_hold.is_(False))
        .all()
    )
    for listing in pending:
        summary["checked"] += 1
        try:
            ok, reasons = evaluate_go_live(db, listing, now)
            if not ok:
                summary["waiting"] += 1
                log.info("recheck: listing %s still waiting: %s", listing.id, "; ".join(reasons))
                continue
            if not listing.seller_id:
                summary["no_seller"] += 1
                log.warning("recheck: listing %s qualifies but has no seller on record; not published", listing.id)
                continue

            listing.is_live = True
            memory_lock.capture(
                db, memory_lock.EventType.AUCTION_OPENED,
                {"listing_id": listing.id, "listing_type": listing.listing_type.value,
                 "starts_at": listing.starts_at.isoformat() + "Z" if listing.starts_at else None,
                 "closes_at": listing.ends_at.isoformat() + "Z" if listing.ends_at else None,
                 "published_by": "daily_recheck"},
                auction_id=listing.id, actor_id=listing.seller_id,
            )
            db.commit()
            record_audit_event(
                db,
                actor_user_id=listing.seller_id,
                entity_type="listing",
                entity_id=listing.id,
                action="published",
                before_state="is_live=False",
                after_state="is_live=True",
                notes="Published automatically by the daily recheck after every gate passed.",
            )
            summary["published"].append(listing.id)
        except Exception:  # noqa: BLE001
            db.rollback()
            summary["errors"] += 1
            log.exception("recheck failed for listing %s; will retry next pass", listing.id)
    return summary
