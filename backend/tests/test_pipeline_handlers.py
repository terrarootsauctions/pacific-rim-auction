from app.services import money, pipeline_handlers as ph, workflow_graph as wg


def fee_fn(sale, bps):
    bps = max(500, min(800, bps))
    return money.fee_minor(sale, bps), bps


def run(**facts):
    base = {"asset_exists": True, "asset_status": "verified", "category": "real_property",
            "gate_ok": True, "gate_reasons": [], "handed_to_terraroots": False,
            "listing_exists": False, "listing_is_live": False, "listing_closed": False,
            "winning_bid_minor": None, "fee_bps": 500, "transaction_status": None}
    base.update(facts)
    return wg.run(wg.platform_pipeline(), "registry_scan", ph.make_handlers(base, fee_fn),
                  approvals=ph.approvals_for(base))


def test_physical_property_waits_for_terraroots_handoff():
    r = run()
    assert r.status == "paused" and r.waiting_on == "terraroots_handoff"
    assert "/entities/handoff" in r.reason


def test_non_physical_skips_handoff_and_waits_for_listing():
    r = run(category="financial")
    assert r.waiting_on == "valuation_listing" and "POST /listings/" in r.reason


def test_unverified_asset_cannot_be_listed_yet():
    r = run(category="financial", asset_status="under_review")
    assert r.waiting_on == "valuation_listing" and "VERIFIED" in r.reason


def test_failed_gate_blocks_and_never_reaches_listing():
    r = run(gate_ok=False, gate_reasons=["Jurisdiction has not been cleared by legal review."])
    assert r.status == "completed" and r.trace[-1]["node"] == "blocked"


def test_rejected_asset_is_blocked_even_if_gate_says_ok():
    r = run(asset_status="rejected")
    assert r.trace[-1]["node"] == "blocked"


def test_listing_not_live_waits_for_human_approval():
    r = run(handed_to_terraroots=True, listing_exists=True)
    assert r.status == "paused" and r.waiting_on == "listing_approval"


def test_live_listing_waits_for_auction_close():
    r = run(handed_to_terraroots=True, listing_exists=True, listing_is_live=True)
    assert r.waiting_on == "marketplace_close" and "not closed" in r.reason


def test_closed_sale_reports_expected_fee_but_not_revenue():
    r = run(handed_to_terraroots=True, listing_exists=True, listing_is_live=True,
            listing_closed=True, winning_bid_minor=100_000_00, fee_bps=650)
    assert r.status == "completed"
    assert r.context["expected_fee_minor"] == 6_500_00
    assert r.context["revenue_confirmed"] is False


def test_revenue_confirmed_only_when_bank_confirmed():
    r = run(handed_to_terraroots=True, listing_exists=True, listing_is_live=True, listing_closed=True,
            winning_bid_minor=100_000_00, fee_bps=650, transaction_status="fee_collected")
    assert r.context["revenue_confirmed"] is True


def test_fee_bps_is_clamped_into_mandated_band():
    r = run(handed_to_terraroots=True, listing_exists=True, listing_is_live=True, listing_closed=True,
            winning_bid_minor=100_000_00, fee_bps=100)
    assert r.context["fee_bps"] == 500


def test_unsold_auction_has_zero_fee():
    r = run(handed_to_terraroots=True, listing_exists=True, listing_is_live=True, listing_closed=True)
    assert r.context["unsold"] is True and r.context["expected_fee_minor"] == 0


def test_missing_asset_fails_cleanly():
    r = run(asset_exists=False)
    assert r.status == "failed" and "Asset not found" in r.error


def test_approval_is_never_assumed():
    assert ph.approvals_for({"listing_is_live": False}) == set()
    assert ph.approvals_for({"listing_is_live": True}) == {"listing_approval"}
