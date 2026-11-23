import pytest

from app.services import listing_gate as lg
from app.services import signing_chain as sc

DOC = sc.sha256_hex(b"agreement")


def signed_chain():
    chain = []
    for event_type, actor in ((sc.EVENT_DOCUMENT_CREATED, "system"),
                              (sc.EVENT_CONSENT_GIVEN, "o@example.com"),
                              (sc.EVENT_SIGNED, "o@example.com")):
        chain.append(sc.new_event(chain, event_type, actor, "2026-11-22T00:00:00Z", DOC))
    return chain


def test_no_candidates_reports_no_lawful_basis():
    ok, reasons, used = lg.check_any(True, "cleared", [])
    assert not ok and used is None and any("lawful basis" in r for r in reasons)


def test_any_passing_candidate_allows_listing():
    candidates = [
        {"basis": lg.BASIS_COURT_ORDER, "reference": ""},
        {"basis": lg.BASIS_OWNER_AUTHORIZATION, "signing_events": signed_chain(), "document_sha256": DOC},
    ]
    ok, reasons, used = lg.check_any(True, "cleared", candidates)
    assert ok and reasons == [] and used == lg.BASIS_OWNER_AUTHORIZATION


def test_failing_candidates_return_shortest_reason_list():
    candidates = [{"basis": lg.BASIS_COURT_ORDER, "reference": ""}, {"basis": lg.BASIS_SELLER_TITLE}]
    ok, reasons, used = lg.check_any(True, "cleared", candidates)
    assert not ok and used is None and len(reasons) == 1


def test_candidates_cannot_override_uncleared_jurisdiction():
    candidates = [{"basis": lg.BASIS_COURT_ORDER, "reference": "Case 1"}]
    ok, reasons, _ = lg.check_any(False, "cleared", candidates)
    assert not ok


def test_validate_basis_record():
    assert lg.validate_basis_record(lg.BASIS_COURT_ORDER, " Case 24-1 ") == "Case 24-1"
    assert lg.validate_basis_record(lg.BASIS_SELLER_TITLE, None) == ""
    for bad in (lg.BASIS_OWNER_AUTHORIZATION, "other"):
        with pytest.raises(ValueError):
            lg.validate_basis_record(bad, "x")
    with pytest.raises(ValueError):
        lg.validate_basis_record(lg.BASIS_GOVERNMENT_AUTHORITY, "  ")
