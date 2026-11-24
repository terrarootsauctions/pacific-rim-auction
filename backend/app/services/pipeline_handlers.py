"""
Pipeline handlers (PURE, standard library only).

Connects the workflow graph to the platform's REAL state. Each handler reads
a plain `facts` dict (built from the database by pipeline_runner.py) and
either returns, or raises Waiting with the exact human action needed. The
handlers change nothing: creating a handoff, creating a listing and
publishing it stay with the people and endpoints that already own them, and
those endpoints enforce the Do No Harm / Follow the Laws gates.

facts keys:
  asset_exists, asset_status, category, gate_ok, gate_reasons,
  handed_to_terraroots, listing_exists, listing_is_live, listing_closed,
  winning_bid_minor, fee_bps, transaction_status
"""
from typing import Callable, Dict, Set

from app.services.workflow_graph import Waiting

BLOCKING_STATUSES = frozenset({"rejected", "withdrawn"})


def make_handlers(facts: dict, fee_fn: Callable[[int, int], tuple]) -> Dict[str, Callable]:
    """fee_fn(sale_minor, stored_bps) -> (fee_minor, bps_used); the platform
    passes fees.calculate_fee_minor_from_bps so the mandated band applies."""

    def registry_scan(ctx):
        if not facts.get("asset_exists"):
            raise ValueError("Asset not found.")
        return {"scanned": True, "category": facts.get("category"), "asset_status": facts.get("asset_status")}

    def compliance_gate(ctx):
        if facts.get("asset_status") in BLOCKING_STATUSES:
            return "blocked"
        return "cleared" if facts.get("gate_ok") else "blocked"

    def route_property(ctx):
        return "physical" if facts.get("category") == "real_property" else "other"

    def terraroots_handoff(ctx):
        if not facts.get("handed_to_terraroots"):
            raise Waiting("A reviewer must record the handoff to TerraRoots (POST /entities/handoff).")
        return {"handed_to_terraroots": True}

    def valuation_listing(ctx):
        if not facts.get("listing_exists"):
            if facts.get("asset_status") != "verified":
                raise Waiting(f"The asset is '{facts.get('asset_status')}'. It must be VERIFIED before a listing can be created.")
            raise Waiting("Create the listing for this verified asset (POST /listings/).")
        return {"listing_exists": True}

    def marketplace_close(ctx):
        if not facts.get("listing_closed"):
            raise Waiting("The auction has not closed yet. It closes on its own at its end time.")
        return {"closed": True, "unsold": not facts.get("winning_bid_minor")}

    def record_expected_fee(ctx):
        sale = facts.get("winning_bid_minor")
        if not sale:
            return {"expected_fee_minor": 0, "revenue_confirmed": False}
        fee, bps = fee_fn(int(sale), int(facts.get("fee_bps") or 0))
        return {
            "expected_fee_minor": fee,
            "fee_bps": bps,
            # Revenue is real only when First Hawaiian Bank has confirmed the exact credit.
            "revenue_confirmed": facts.get("transaction_status") == "fee_collected",
        }

    return {
        "registry_scan": registry_scan,
        "compliance_gate": compliance_gate,
        "route_property": route_property,
        "terraroots_handoff": terraroots_handoff,
        "valuation_listing": valuation_listing,
        "marketplace_close": marketplace_close,
        "record_expected_fee": record_expected_fee,
    }


def approvals_for(facts: dict) -> Set[str]:
    """The listing approval is the existing human publish step: it counts as
    given only once the listing is actually live (publish enforces the gates)."""
    return {"listing_approval"} if facts.get("listing_is_live") else set()
