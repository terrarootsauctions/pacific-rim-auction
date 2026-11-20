"""
Compliance service - enforces the platform's mandatory rules:

1. A REAL_PROPERTY listing (claimed by the umbrella, passed through
   TerraRoots Global Realty Solutions LLC, and sold on the Pacific Rim
   Auctions LLC real estate marketplace) cannot go live until property
   condition, air quality, AND mineral rights inspections are all
   COMPLETED and DISCLOSED to the buyer prior to closing.
2. Every listing must pass "do no harm" and jurisdiction (laws of the land)
   checks at the asset level before a listing can be created from it.

These functions are the single source of truth for "is this allowed to go
live" - API routes call into this rather than re-implementing the checks.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import AssetCategory, InspectionStatus, InspectionType
from app.models.jurisdiction_node import JurisdictionNode, NodeStatus
from app.models.listing import Inspection, Listing
from app.services.audit import record_audit_event
from app.services.precedent import apply_precedent, build_match_key, find_precedent

REQUIRED_INSPECTIONS_FOR_REAL_PROPERTY = [
    InspectionType.PROPERTY_CONDITION,
    InspectionType.AIR_QUALITY,
    InspectionType.MINERAL_RIGHTS,
]


def get_jurisdiction_node(db: Session, country_code: str, region_code: str = None) -> Optional[JurisdictionNode]:
    """Looks up the specific node for an asset's location - this is the
    real mechanism behind 'follow the laws of the land' across 190
    countries: a per-region lookup, not a single global rule."""
    query = db.query(JurisdictionNode).filter(JurisdictionNode.country_code == country_code)
    if region_code:
        query = query.filter(JurisdictionNode.region_code == region_code)
    else:
        query = query.filter(JurisdictionNode.region_code.is_(None))
    return query.first()


def check_jurisdiction_with_precedent(
    db: Session,
    node: JurisdictionNode,
    reason_code: str,
    source: str,
    actor_user_id: str,
) -> Tuple[str, str]:
    """The real implementation of the architect's directive: if this
    EXACT failure (same country, same region, same reason_code, same
    source) has already been resolved by a human before, apply that
    resolution automatically and log the reuse. Otherwise, this is
    genuinely new - record it as a fresh CHECK_FAILED for human review,
    same as always.

    Returns (outcome, detail) where outcome is "precedent_applied" or
    "new_failure_recorded"."""
    match_key = build_match_key(
        country=node.country_code,
        region=node.region_code or "national",
        reason=reason_code,
        source=source,
    )

    precedent = find_precedent(db, "jurisdiction_node", "check_failed", match_key)

    if precedent:
        node.status = precedent.resolution_status  # type: ignore[assignment]
        from datetime import datetime

        node.last_check_failure_reason = reason_code
        node.last_check_source = source
        node.last_check_failed_at = datetime.utcnow()
        db.commit()
        apply_precedent(db, precedent, entity_id=node.id)
        return "precedent_applied", (
            f"This exact case (key={match_key}) was already resolved on "
            f"{precedent.resolved_at.isoformat() if precedent.resolved_at else 'unknown'} "
            f"by user {precedent.resolved_by_user_id}. Applied that resolution: "
            f"{precedent.resolution_status}."
        )

    # No precedent - this is genuinely new. Record it as a failure for a
    # human to review, exactly as before.
    record_check_failure(db, node, reason=reason_code, source=source, actor_user_id=actor_user_id)
    return "new_failure_recorded", (
        f"No precedent exists for key={match_key}. Recorded as a new "
        f"CHECK_FAILED node, pending human review."
    )


def record_check_failure(
    db: Session,
    node: JurisdictionNode,
    reason: str,
    source: str,
    actor_user_id: str,
) -> JurisdictionNode:
    """Records a real compliance/legal check failure on a jurisdiction
    node. Per the architect's directive: failures are kept as a permanent
    record, never silently discarded. This moves the node to CHECK_FAILED,
    which blocks any listing in that jurisdiction until a human reviews
    the failure and re-runs the check - it does not delete or hide
    anything about what was attempted."""
    before = f"status={node.status.value}"
    node.status = NodeStatus.CHECK_FAILED
    node.last_check_failure_reason = reason
    node.last_check_source = source
    from datetime import datetime

    node.last_check_failed_at = datetime.utcnow()
    db.commit()
    db.refresh(node)

    record_audit_event(
        db,
        actor_user_id=actor_user_id,
        entity_type="jurisdiction_node",
        entity_id=node.id,
        action="check_failed",
        before_state=before,
        after_state=f"status=check_failed, reason={reason}, source={source}",
    )

    return node


def jurisdiction_node_cleared(db: Session, country_code: str, region_code: str = None) -> Tuple[bool, str]:
    """A jurisdiction node existing in the table is NOT the same as it
    being cleared. Only ACTIVE status (real legal review completed)
    clears it. This is the guardrail that keeps 'build the structure
    ahead of need' from quietly becoming 'approve ahead of review.'"""
    node = get_jurisdiction_node(db, country_code, region_code)
    if not node:
        return False, f"No jurisdiction node found for {country_code}/{region_code or 'national'}."
    if node.status == NodeStatus.ACTIVE:
        return True, "OK"
    if node.status == NodeStatus.PENDING_REVIEW:
        return False, f"Jurisdiction node for {country_code}/{region_code or 'national'} has not completed legal review yet."
    if node.status == NodeStatus.RESTRICTED:
        return False, f"Jurisdiction node for {country_code}/{region_code or 'national'} is RESTRICTED: {node.disclosure_requirements or 'see node record'}"
    if node.status == NodeStatus.CHECK_FAILED:
        return False, (
            f"Jurisdiction node for {country_code}/{region_code or 'national'} has a "
            f"recorded check failure ({node.last_check_source or 'unknown source'}: "
            f"{node.last_check_failure_reason or 'no reason recorded'}). This record is "
            f"kept permanently and requires human review before re-checking."
        )
    return False, f"Jurisdiction node for {country_code}/{region_code or 'national'} is SUSPENDED."


def asset_cleared_for_listing(asset: Asset) -> Tuple[bool, str]:
    """Check the do-no-harm / jurisdiction gates required before any
    listing can be created from this asset."""
    if asset.do_no_harm_cleared != "cleared":
        return False, "Asset has not cleared do-no-harm review."
    if asset.jurisdiction_cleared != "cleared":
        return False, "Asset has not cleared jurisdiction (laws of the land) review."
    return True, "OK"


def listing_requires_inspection(asset: Asset) -> bool:
    return asset.category == AssetCategory.REAL_PROPERTY


def create_required_inspections(db: Session, listing: Listing) -> None:
    """Stamp out the three required-but-not-yet-done inspection records
    for a freshly created real-property listing."""
    for itype in REQUIRED_INSPECTIONS_FOR_REAL_PROPERTY:
        db.add(
            Inspection(
                listing_id=listing.id,
                inspection_type=itype,
                status=InspectionStatus.REQUIRED,
            )
        )
    db.commit()


def listing_cleared_to_go_live(db: Session, listing: Listing) -> Tuple[bool, str]:
    """The master gate checked before is_live can ever be set True."""
    if not listing.requires_inspection:
        return True, "OK"

    inspections = db.query(Inspection).filter(Inspection.listing_id == listing.id).all()
    present_types = {i.inspection_type for i in inspections}

    missing = [t for t in REQUIRED_INSPECTIONS_FOR_REAL_PROPERTY if t not in present_types]
    if missing:
        return False, f"Missing required inspections: {[m.value for m in missing]}"

    not_disclosed = [
        i.inspection_type.value
        for i in inspections
        if i.inspection_type in REQUIRED_INSPECTIONS_FOR_REAL_PROPERTY
        and i.status != InspectionStatus.DISCLOSED
    ]
    if not_disclosed:
        return False, f"Inspections not yet completed+disclosed: {not_disclosed}"

    return True, "OK"
