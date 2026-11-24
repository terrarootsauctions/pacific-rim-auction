import random
from datetime import datetime, timedelta, timezone

import pytest

from app.services import (
    account_validation as av, anomaly, fhb_rail, ledger_consolidation as lc, market_sim, optimizer,
    workflow_graph as wg,
)


# ---- identifiers ----------------------------------------------------------

def test_aba_checksum():
    assert av.aba_checksum_ok("121301015")
    assert not av.aba_checksum_ok("121301016")
    assert not av.aba_checksum_ok("12130101")
    assert not av.aba_checksum_ok("abcdefghi")


def test_iban_and_swift():
    assert av.iban_ok("GB82 WEST 1234 5698 7654 32")
    assert not av.iban_ok("GB82 WEST 1234 5698 7654 33")
    assert av.swift_format_ok("FHBKUS77")
    assert av.swift_format_ok("DEUTDEFF500")
    assert not av.swift_format_ok("FHB")


# ---- BAI2 / cutoffs / sweep ----------------------------------------------

BAI2 = """01,SENDER,RECEIVER,261122,0700,1,80,,2/
02,RECEIVER,ORIG,1,261122,0700,USD,2/
03,9999000011,USD,010,500000,,,015,500000,,/
16,165,50000,0,BANKREF1,PRA-ABC123,Fee credit/
88,continued text
16,475,2500,0,BANKREF2,,Bank charge/
49,1000000,3/
98,1000000,1,5/
99,1000000,1,7/
"""


def test_bai2_parse_credits_and_debits():
    out = fhb_rail.parse_bai2(BAI2)
    assert out["credit_count"] == 1
    assert out["credit_total_minor"] == 50000
    assert out["debit_count"] == 1
    assert out["account_suffix"] == "0011"
    c = out["credits"][0]
    assert c["customer_reference"] == "PRA-ABC123"
    assert c["bank_reference"] == "BANKREF1"
    assert "continued text" in c["memo"]


def test_bai2_rejects_garbage():
    with pytest.raises(ValueError):
        fhb_rail.parse_bai2("hello")


def test_cutoff_weekday_before_and_after():
    # Monday 2026-11-23 08:00 HST = 18:00 UTC
    early = fhb_rail.cutoff_status(datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc))
    assert early["domestic"]["open_now"] and early["foreign"]["open_now"]
    assert early["domestic"]["minutes_until_next"] == 150
    # Monday 12:00 HST: domestic closed, foreign open
    noon = fhb_rail.cutoff_status(datetime(2026, 11, 23, 22, 0, tzinfo=timezone.utc))
    assert not noon["domestic"]["open_now"] and noon["foreign"]["open_now"]


def test_cutoff_weekend_rolls_to_monday():
    sat = fhb_rail.cutoff_status(datetime(2026, 11, 28, 20, 0, tzinfo=timezone.utc))
    assert not sat["business_day"]
    assert sat["domestic"]["next_cutoff_hst"].startswith("2026-11-30")


def test_sweep_plan_never_executes():
    plan = fhb_rail.sweep_plan({"a": 100, "b": 0, "c": 250})
    assert plan["execute"] is False
    assert plan["total_minor"] == 350
    assert len(plan["lines"]) == 2
    with pytest.raises(TypeError):
        fhb_rail.sweep_plan({"a": 1.5})


# ---- workflow graph -------------------------------------------------------

def _handlers(gate="cleared", route="physical"):
    return {
        "registry_scan": lambda c: {"scanned": True},
        "compliance_gate": lambda c: gate,
        "route_property": lambda c: route,
        "terraroots_handoff": lambda c: {"handed_off": True},
        "valuation_listing": lambda c: {"listed": True},
        "marketplace_close": lambda c: {"closed": True},
        "record_expected_fee": lambda c: {"fee_recorded": True},
    }


def test_pipeline_is_sound():
    assert wg.validate(wg.platform_pipeline(), "registry_scan", _handlers()) == []


def test_pipeline_pauses_for_approval_then_completes():
    g = wg.platform_pipeline()
    first = wg.run(g, "registry_scan", _handlers())
    assert first.status == "paused" and first.waiting_on == "listing_approval"
    assert first.context.get("handed_off") and not first.context.get("closed")
    second = wg.run(g, "listing_approval", _handlers(), first.context,
                    approvals={"listing_approval"}, entry="registry_scan")
    assert second.status == "completed" and second.context["fee_recorded"]


def test_blocked_asset_stops_at_gate():
    res = wg.run(wg.platform_pipeline(), "registry_scan", _handlers(gate="blocked"))
    assert res.status == "completed"
    assert res.trace[-1]["node"] == "blocked"
    assert not res.context.get("listed")


def test_non_physical_skips_terraroots():
    res = wg.run(wg.platform_pipeline(), "registry_scan", _handlers(route="other"))
    assert res.status == "paused" and not res.context.get("handed_off")


def test_handler_error_stops_run():
    h = _handlers()
    h["registry_scan"] = lambda c: 1 / 0
    res = wg.run(wg.platform_pipeline(), "registry_scan", h)
    assert res.status == "failed" and "registry_scan" in res.error


def test_step_limit_and_invalid_graph():
    g = wg.Graph()
    g.add(wg.Node("a", "agent", "", "h")).add(wg.Node("b", "agent", "", "h"))
    g.link("a", "b").link("b", "a")
    res = wg.run(g, "a", {"h": lambda c: {}}, max_steps=5)
    assert res.status == "step_limit"
    bad = wg.Graph().add(wg.Node("x", "agent", "", "missing"))
    assert wg.run(bad, "x", {}).status == "failed"


# ---- anomaly --------------------------------------------------------------

def test_anomaly_flags():
    now = datetime(2026, 11, 23, 12, 0)
    quiet = [(now - timedelta(hours=h, minutes=5), 10000, True) for h in range(2, 26)]
    assert anomaly.detect(quiet, now) == []
    burst = quiet + [(now - timedelta(minutes=i), 10000, i % 2 == 0) for i in range(1, 21)]
    kinds = {f["kind"] for f in anomaly.detect(burst, now)}
    assert {"volume_spike", "bad_signature_rate"} <= kinds
    big = quiet + [(now - timedelta(minutes=3), 5_000_000, True)]
    assert {f["kind"] for f in anomaly.detect(big, now)} == {"amount_outlier"}


# ---- optimizer ------------------------------------------------------------

def test_optimizer_exact_small():
    items = [optimizer.Item("a", 60, 10, "US"), optimizer.Item("b", 100, 20, "US"),
             optimizer.Item("c", 120, 30, "JP")]
    out = optimizer.solve(items, 50)
    assert out["method"] == "exact"
    assert out["total_value_minor"] == 220 and set(out["chosen"]) == {"b", "c"}


def test_optimizer_country_cap():
    items = [optimizer.Item(str(i), 100, 1, "US") for i in range(3)] + [optimizer.Item("j", 10, 1, "JP")]
    out = optimizer.solve(items, 100, per_country_cap=1)
    assert out["total_value_minor"] == 110


def test_annealing_matches_exact_on_random_case():
    rng = random.Random(3)
    items = [optimizer.Item(str(i), rng.randint(10, 500), rng.randint(5, 100), rng.choice("ABC"))
             for i in range(14)]
    exact = optimizer.solve(items, 300, 3)["total_value_minor"]
    ann = optimizer._anneal(items, 300, 3, seed=7, iterations=30000)
    assert sum(i.value_minor for i in ann) >= 0.95 * exact
    assert optimizer._feasible(ann, 300, 3)


def test_annealing_is_deterministic_and_feasible_for_large():
    rng = random.Random(5)
    items = [optimizer.Item(str(i), rng.randint(10, 500), rng.randint(5, 100), rng.choice("ABCDE"))
             for i in range(40)]
    a = optimizer.solve(items, 800, 4)
    b = optimizer.solve(items, 800, 4)
    assert a == b and a["method"] == "annealing" and a["total_cost_minor"] <= 800


# ---- simulator / ledger ---------------------------------------------------

def test_simulation_deterministic_and_fee_band_ordering():
    a = market_sim.simulate(2000, 10_000_000)
    b = market_sim.simulate(2000, 10_000_000)
    assert a == b
    fees = a["estimated_fee_total_minor_by_bps"]
    assert fees[500] < fees[650] < fees[800]
    assert 0 < a["sold_rate"] <= 1
    assert a["price_p10_minor"] <= a["price_p50_minor"] <= a["price_p90_minor"]
    with pytest.raises(ValueError):
        market_sim.simulate(0, 100)


def test_ledger_consolidation():
    rows = [
        ("pacific_rim_auctions_llc", "BANK_CASH", 500, 0),
        ("pacific_rim_auctions_llc", "REVENUE", 0, 500),
        ("pacific_rim_auctions", "INTERCO_TERRAROOTS", 200, 0),
        ("terraroots", "INTERCO_UMBRELLA", 0, 200),
    ]
    out = lc.consolidate(rows)
    assert out["balanced"]
    assert out["intercompany_residual_minor"] == 0
    assert out["consolidated"] == {"BANK_CASH": 500, "REVENUE": -500}
    off = lc.consolidate([("a", "INTERCO_X", 100, 0), ("b", "INTERCO_Y", 0, 90), ("b", "CASH", 0, 10)])
    assert off["intercompany_residual_minor"] == 10 and off["balanced"]
    with pytest.raises(TypeError):
        lc.consolidate([("a", "CASH", 1.5, 0)])
