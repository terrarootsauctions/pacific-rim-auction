from app.services import listing_gate as lg
from app.services import signing_chain as sc

DOC = sc.sha256_hex(b"authorization agreement v1")


def signed_chain():
    chain = []
    for event_type, actor in (
        (sc.EVENT_DOCUMENT_CREATED, "system"),
        (sc.EVENT_CONSENT_GIVEN, "owner@example.com"),
        (sc.EVENT_SIGNED, "owner@example.com"),
    ):
        chain.append(sc.new_event(chain, event_type, actor, "2026-11-22T00:00:00Z", DOC))
    return chain


def test_owner_authorization_with_signature_is_allowed():
    ok, reasons = lg.check_listing(True, "cleared", lg.BASIS_OWNER_AUTHORIZATION,
                                   signing_events=signed_chain(), document_sha256=DOC)
    assert ok and reasons == []


def test_owner_authorization_without_signature_is_refused():
    ok, reasons = lg.check_listing(True, "cleared", lg.BASIS_OWNER_AUTHORIZATION,
                                   signing_events=[], document_sha256=DOC)
    assert not ok and any("signature" in r for r in reasons)


def test_tampered_signature_is_refused():
    chain = signed_chain()
    chain[1] = {**chain[1], "actor": "someone.else@example.com"}
    ok, _ = lg.check_listing(True, "cleared", lg.BASIS_OWNER_AUTHORIZATION,
                             signing_events=chain, document_sha256=DOC)
    assert not ok


def test_seller_title_needs_confirmation():
    assert lg.check_listing(True, "cleared", lg.BASIS_SELLER_TITLE, seller_holds_title=True)[0]
    assert not lg.check_listing(True, "cleared", lg.BASIS_SELLER_TITLE)[0]


def test_government_and_court_bases_need_a_reference():
    for basis in (lg.BASIS_GOVERNMENT_AUTHORITY, lg.BASIS_COURT_ORDER):
        assert lg.check_listing(True, "cleared", basis, reference="Case 24-1234")[0]
        assert not lg.check_listing(True, "cleared", basis, reference="   ")[0]
        assert not lg.check_listing(True, "cleared", basis)[0]


def test_no_basis_is_refused():
    for basis in (None, "", "because_i_said_so"):
        ok, reasons = lg.check_listing(True, "cleared", basis)
        assert not ok and any("lawful basis" in r for r in reasons)


def test_uncleared_jurisdiction_blocks_every_basis():
    ok, reasons = lg.check_listing(False, "cleared", lg.BASIS_COURT_ORDER, reference="Case 1")
    assert not ok and any("Jurisdiction" in r for r in reasons)


def test_do_no_harm_must_be_cleared():
    for status in ("pending", "flagged", ""):
        ok, reasons = lg.check_listing(True, status, lg.BASIS_COURT_ORDER, reference="Case 1")
        assert not ok and any("Do No Harm" in r for r in reasons)


def test_all_missing_conditions_are_reported_together():
    ok, reasons = lg.check_listing(False, "pending", None)
    assert not ok and len(reasons) == 3
