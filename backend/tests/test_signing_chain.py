import copy

import pytest

from app.services import signing_chain as sc

DOC = sc.sha256_hex(b"authorization agreement v1")
OTHER_DOC = sc.sha256_hex(b"a different agreement")


def build_signed_chain():
    chain = []
    steps = [
        (sc.EVENT_DOCUMENT_CREATED, "system", "2026-11-22T00:00:00Z"),
        (sc.EVENT_SENT, "system", "2026-11-22T00:01:00Z"),
        (sc.EVENT_VIEWED, "owner@example.com", "2026-11-22T01:00:00Z"),
        (sc.EVENT_CONSENT_GIVEN, "owner@example.com", "2026-11-22T01:02:00Z"),
        (sc.EVENT_SIGNED, "owner@example.com", "2026-11-22T01:03:00Z"),
    ]
    for event_type, actor, when in steps:
        chain.append(sc.new_event(chain, event_type, actor, when, DOC))
    return chain


def test_signed_chain_verifies_and_authorizes():
    chain = build_signed_chain()
    assert sc.verify_chain(chain) == (True, None)
    assert sc.is_authorized(chain, DOC)


def test_wrong_document_is_not_authorized():
    assert not sc.is_authorized(build_signed_chain(), OTHER_DOC)


def test_unsigned_chain_is_not_authorized():
    chain = build_signed_chain()[:4]
    assert sc.verify_chain(chain) == (True, None)
    assert not sc.is_authorized(chain, DOC)


def test_empty_chain_is_not_authorized():
    assert not sc.is_authorized([], DOC)


def test_tampering_with_any_event_is_detected():
    for index in range(5):
        chain = build_signed_chain()
        chain[index] = copy.deepcopy(chain[index])
        chain[index]["actor"] = "someone.else@example.com"
        ok, bad = sc.verify_chain(chain)
        assert not ok and bad == index
        assert not sc.is_authorized(chain, DOC)


def test_removing_an_event_is_detected():
    chain = build_signed_chain()
    del chain[2]
    ok, bad = sc.verify_chain(chain)
    assert not ok and bad == 2


def test_rewriting_hashes_after_a_change_still_fails_later_events():
    chain = build_signed_chain()
    forged = copy.deepcopy(chain[1])
    forged["actor"] = "attacker"
    body = {k: forged[k] for k in (
        "index", "event_type", "actor", "occurred_at",
        "document_sha256", "detail", "prev_hash",
    )}
    forged["event_hash"] = sc.compute_event_hash(forged["prev_hash"], body)
    chain[1] = forged
    ok, bad = sc.verify_chain(chain)
    assert not ok and bad == 2


def test_signature_requires_consent():
    chain = []
    chain.append(sc.new_event(chain, sc.EVENT_DOCUMENT_CREATED, "system", "t0", DOC))
    with pytest.raises(ValueError):
        sc.new_event(chain, sc.EVENT_SIGNED, "owner@example.com", "t1", DOC)


def test_closed_chain_accepts_no_more_events():
    chain = build_signed_chain()
    with pytest.raises(ValueError):
        sc.new_event(chain, sc.EVENT_VIEWED, "owner@example.com", "t9", DOC)


def test_declined_chain_is_closed_and_not_authorized():
    chain = []
    chain.append(sc.new_event(chain, sc.EVENT_DOCUMENT_CREATED, "system", "t0", DOC))
    chain.append(sc.new_event(chain, sc.EVENT_DECLINED, "owner@example.com", "t1", DOC))
    assert not sc.is_authorized(chain, DOC)
    with pytest.raises(ValueError):
        sc.new_event(chain, sc.EVENT_SIGNED, "owner@example.com", "t2", DOC)


def test_event_for_a_different_document_is_refused():
    chain = build_signed_chain()[:2]
    with pytest.raises(ValueError):
        sc.new_event(chain, sc.EVENT_VIEWED, "owner@example.com", "t3", OTHER_DOC)


def test_unknown_event_type_and_missing_actor_are_refused():
    with pytest.raises(ValueError):
        sc.new_event([], "approved", "system", "t0", DOC)
    with pytest.raises(ValueError):
        sc.new_event([], sc.EVENT_SENT, "", "t0", DOC)


def test_certificate_matches_chain():
    chain = build_signed_chain()
    cert = sc.completion_certificate(chain)
    assert cert["signed"] is True
    assert cert["chain_intact"] is True
    assert cert["event_count"] == 5
    assert cert["final_hash"] == chain[-1]["event_hash"]
    assert cert["signed_by"] == "owner@example.com"


def test_certificate_of_tampered_chain_is_not_signed():
    chain = build_signed_chain()
    chain[0] = {**chain[0], "occurred_at": "1999-01-01T00:00:00Z"}
    cert = sc.completion_certificate(chain)
    assert cert["chain_intact"] is False
    assert cert["signed"] is False


def test_hashes_are_deterministic():
    assert build_signed_chain() == build_signed_chain()
