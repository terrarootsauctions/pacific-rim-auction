"""
Pipeline runner: reads an asset's real state from the database and reports
where it stands in the pipeline and what the next human action is.

READ-ONLY. It never creates, approves, publishes or pays anything. It reuses
the platform's existing gate (publisher.evaluate_asset_gate), so the Do No
Harm and Follow the Laws checks are the same ones the publish step applies.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.entity_handoff import EntityHandoff
from app.models.enums import AssetStatus
from app.models.listing import Listing
from app.models.transaction import Transaction
from app.services import entities, fees, pipeline_handlers, publisher, workflow_graph

TERMINAL_STATUSES = (AssetStatus.SOLD, AssetStatus.REJECTED, AssetStatus.WITHDRAWN)


def load_facts(db: Session, asset_id: str) -> dict:
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None:
        return {"asset_exists": False}
    gate_ok, gate_reasons, _basis = publisher.evaluate_asset_gate(db, asset)
    handed = (
        db.query(EntityHandoff.id)
        .filter(EntityHandoff.asset_id == asset.id, EntityHandoff.to_entity == entities.TERRAROOTS)
        .first() is not None
    )
    listing = db.query(Listing).filter(Listing.asset_id == asset.id).first()
    tx = None
    if listing is not None:
        tx = (
            db.query(Transaction).filter(Transaction.listing_id == listing.id)
            .order_by(Transaction.created_at.desc()).first()
        )
    return {
        "asset_exists": True,
        "asset_status": asset.status.value,
        "category": asset.category.value,
        "gate_ok": bool(gate_ok),
        "gate_reasons": list(gate_reasons or []),
        "handed_to_terraroots": handed,
        "listing_exists": listing is not None,
        "listing_is_live": bool(listing and listing.is_live),
        "listing_closed": bool(listing and listing.closed_at is not None),
        "winning_bid_minor": listing.winning_bid_minor if listing else None,
        "fee_bps": listing.platform_fee_rate_bps if listing else None,
        "transaction_status": tx.status.value if tx is not None else None,
    }


def position(db: Session, asset_id: str) -> dict:
    facts = load_facts(db, asset_id)
    graph = workflow_graph.platform_pipeline()
    handlers = pipeline_handlers.make_handlers(facts, fees.calculate_fee_minor_from_bps)
    result = workflow_graph.run(
        graph, "registry_scan", handlers, approvals=pipeline_handlers.approvals_for(facts),
    )
    blocked = bool(result.trace) and result.trace[-1].get("node") == "blocked"
    return {
        "asset_id": asset_id,
        "status": "blocked" if blocked else result.status,
        "stopped_at": result.waiting_on or (result.trace[-1]["node"] if result.trace else None),
        "next_action": result.reason or (
            "; ".join(facts.get("gate_reasons") or ["Blocked by the compliance gate."]) if blocked else None
        ),
        "error": result.error,
        "expected_fee_minor": result.context.get("expected_fee_minor"),
        "revenue_confirmed": result.context.get("revenue_confirmed"),
        "trace": result.trace,
    }


def open_assets(db: Session, limit: int = 100) -> List[dict]:
    """Where every non-final asset stands, so the architect sees at a glance
    what needs a human. Capped for safety."""
    ids = [
        a.id for a in db.query(Asset.id, Asset.status)
        .filter(~Asset.status.in_(TERMINAL_STATUSES)).order_by(Asset.created_at).limit(limit).all()
    ]
    return [position(db, i) for i in ids]
