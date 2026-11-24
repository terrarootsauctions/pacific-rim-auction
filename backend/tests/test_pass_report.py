from app.services import pass_report as pr


def pos(aid, status="paused", stop="terraroots_handoff", action="Record the handoff.", revenue=False):
    return {"asset_id": aid, "status": status, "stopped_at": stop, "next_action": action,
            "revenue_confirmed": revenue}


def test_first_pass_marks_everything_new_and_builds_snapshot():
    r = pr.compare(None, [pos("a"), pos("b", stop="valuation_listing")])
    assert r["first_pass"] and r["counts"]["new"] == 2
    assert r["snapshot"]["assets"]["a"]["stopped_at"] == "terraroots_handoff"
    assert r["waiting_by_action"] == {"Record the handoff.": 2}


def test_advance_stall_regress_and_counter():
    p1 = pr.compare(None, [pos("a"), pos("b"), pos("c", stop="marketplace_close")])["snapshot"]
    r2 = pr.compare(p1, [pos("a", stop="valuation_listing"), pos("b"), pos("c", stop="listing_approval")])
    assert r2["changes"]["advanced"] == ["a"] and r2["changes"]["regressed"] == ["c"]
    assert [s["asset_id"] for s in r2["changes"]["stalled"]] == ["b"]
    assert r2["changes"]["stalled"][0]["stalled_passes"] == 1
    r3 = pr.compare(r2["snapshot"], [pos("a", stop="valuation_listing"), pos("b"), pos("c", stop="listing_approval")])
    assert {s["asset_id"]: s["stalled_passes"] for s in r3["changes"]["stalled"]} == {"a": 1, "b": 2, "c": 1}


def test_stalled_asset_moves_when_records_update_with_no_trigger():
    snap = pr.compare(None, [pos("a")])["snapshot"]
    snap = pr.compare(snap, [pos("a")])["snapshot"]  # office closed: stalled twice
    r = pr.compare(snap, [pos("a", stop="valuation_listing")])
    assert r["changes"]["advanced"] == ["a"] and r["changes"]["stalled"] == []
    assert r["snapshot"]["assets"]["a"]["stalled_passes"] == 0


def test_blocked_and_unblocked():
    s = pr.compare(None, [pos("a")])["snapshot"]
    r = pr.compare(s, [pos("a", status="blocked", stop="blocked", action="Jurisdiction not cleared.")])
    assert r["changes"]["blocked"] == ["a"]
    again = pr.compare(r["snapshot"], [pos("a", status="blocked", stop="blocked")])
    assert again["changes"]["blocked"] == [] and again["changes"]["stalled"] == []  # already known
    cleared = pr.compare(again["snapshot"], [pos("a", stop="valuation_listing")])
    assert cleared["changes"]["advanced"] == ["a"]


def test_completed_closed_out_and_revenue_confirmation():
    s = pr.compare(None, [pos("a", stop="record_expected_fee"), pos("b")])["snapshot"]
    r = pr.compare(s, [pos("a", status="completed", stop="done", action=None, revenue=True)])
    assert r["changes"]["completed"] == ["a"]
    assert r["changes"]["revenue_confirmed"] == ["a"]
    assert r["changes"]["closed_out"] == ["b"]
    later = pr.compare(r["snapshot"], [pos("a", status="completed", stop="done", action=None, revenue=True)])
    assert later["changes"]["revenue_confirmed"] == [] and later["changes"]["completed"] == []


def test_truncation_flag_and_bad_previous_snapshot():
    assert pr.compare(None, [], truncated=True)["truncated"] is True
    r = pr.compare({"assets": {}}, [pos("a")])
    assert r["counts"]["new"] == 1 and not r["first_pass"]
