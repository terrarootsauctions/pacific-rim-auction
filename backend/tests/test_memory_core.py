import copy

import pytest

from app.services import memory_core as mc

SECRET = "unit-test-secret-not-for-production-0123456789"


def make_chain(n=4):
    key = mc.derive_keys(SECRET)
    records, prev = [], mc.GENESIS_HASH
    for i in range(1, n + 1):
        rec = mc.build_record(
            key, sequence=i, previous_hash=prev, event_type="BID_ACCEPTED",
            event_id=f"evt-{i}", occurred_at=f"2026-11-20T12:00:0{i}Z",
            payload={"amount_minor": 1000 * i, "currency": "USD"},
            metadata={"request": f"r{i}"}, auction_id="a1", bid_id=f"b{i}", actor_id="u1",
        )
        records.append(rec)
        prev = rec["event_hash"]
    return key, records


def test_canonical_json_is_deterministic():
    assert mc.canonical_json({"b": 1, "a": 2}) == mc.canonical_json({"a": 2, "b": 1})


def test_same_secret_gives_same_key_and_different_secret_differs():
    a = mc.derive_keys(SECRET)
    b = mc.derive_keys(SECRET)
    c = mc.derive_keys(SECRET + "x")
    assert mc.public_key_b64(a.ed) == mc.public_key_b64(b.ed)
    assert mc.public_key_b64(a.ed) != mc.public_key_b64(c.ed)
    assert mc.pq_public_key_b64(a) == mc.pq_public_key_b64(b)
    assert mc.pq_public_key_b64(a) != mc.pq_public_key_b64(c)


def test_short_secret_refused():
    with pytest.raises(ValueError):
        mc.derive_keys("short")


def test_clean_chain_verifies():
    key, recs = make_chain()
    result = mc.verify_chain(recs, mc.public_keys_of(key))
    assert result.status == "VERIFIED" and result.checked == 4


def test_empty_chain_verifies_with_zero_checked():
    key, _ = make_chain(1)
    result = mc.verify_chain([], mc.public_keys_of(key))
    assert result.status == "VERIFIED" and result.checked == 0


def test_tampered_payload_is_detected():
    key, recs = make_chain()
    recs[1] = copy.deepcopy(recs[1])
    recs[1]["payload"]["amount_minor"] = 1
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.status == "INTEGRITY_FAILURE"
    assert r.first_failure_sequence == 2 and r.failure_reason == "CONTENT_HASH_MISMATCH"


def test_tampered_metadata_is_detected():
    key, recs = make_chain()
    recs[2]["metadata"] = {"request": "forged"}
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.failure_reason == "METADATA_HASH_MISMATCH" and r.first_failure_sequence == 3


def test_tampered_field_covered_by_event_hash_is_detected():
    key, recs = make_chain()
    recs[0]["actor_id"] = "someone-else"
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.failure_reason == "EVENT_HASH_MISMATCH" and r.first_failure_sequence == 1


def test_rehashing_a_tampered_record_still_fails_on_signature_or_link():
    key, recs = make_chain()
    recs[1]["payload"]["amount_minor"] = 5
    recs[1]["content_hash"] = mc.sha256_hex(mc.canonical_json(recs[1]["payload"]))
    recs[1]["event_hash"] = mc.compute_event_hash(recs[1])
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.status == "INTEGRITY_FAILURE"
    assert r.failure_reason in ("SIGNATURE_INVALID", "PREVIOUS_HASH_MISMATCH")


def test_deleted_record_is_a_sequence_gap():
    key, recs = make_chain()
    del recs[1]
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.failure_reason == "SEQUENCE_GAP" and r.expected == "2" and r.actual == "3"


def test_reordered_records_detected():
    key, recs = make_chain()
    recs[1], recs[2] = recs[2], recs[1]
    assert mc.verify_chain(recs, mc.public_keys_of(key)).status == "INTEGRITY_FAILURE"


def test_wrong_public_key_fails_signature():
    key, recs = make_chain()
    other = mc.derive_keys(SECRET + "different")
    r = mc.verify_chain(recs, mc.public_keys_of(other))
    assert r.failure_reason == "SIGNATURE_INVALID"


def test_manifest_signs_and_detects_change():
    key, recs = make_chain(1)
    sm = mc.build_manifest(key, recs[0], "Pacific Rim Auctions", "1.0.0")
    assert mc.verify_manifest(mc.public_keys_of(key), sm) is True
    assert sm["manifest"]["archive"] == {"status": "NOT_ARCHIVED"}
    sm["manifest"]["archive"] = {"status": "ARCHIVE_CONFIRMED", "id": "forged"}
    assert mc.verify_manifest(mc.public_keys_of(key), sm) is False


def test_every_record_carries_both_signatures():
    key, recs = make_chain(1)
    assert recs[0]["signature_algorithm"] == "Ed25519"
    assert recs[0]["pq_signature_algorithm"] == "ML-DSA-65"
    assert len(recs[0]["pq_signature"]) > 1000


def test_post_quantum_signature_alone_is_enforced():
    key, recs = make_chain()
    # Valid Ed25519 signature kept, post-quantum signature from another key: must fail.
    other = mc.derive_keys(SECRET + "other")
    forged = mc.build_record(
        other, sequence=2, previous_hash=recs[0]["event_hash"], event_type="BID_ACCEPTED",
        event_id="evt-2", occurred_at="2026-11-20T12:00:02Z",
        payload={"amount_minor": 2000, "currency": "USD"}, metadata={"request": "r2"},
        auction_id="a1", bid_id="b2", actor_id="u1",
    )
    recs[1]["pq_signature"] = forged["pq_signature"]
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.status == "INTEGRITY_FAILURE" and r.failure_reason == "PQ_SIGNATURE_INVALID"


def test_missing_pq_signature_fails_when_pq_key_is_required():
    key, recs = make_chain(2)
    recs[0]["pq_signature"] = ""
    r = mc.verify_chain(recs, mc.public_keys_of(key))
    assert r.failure_reason == "PQ_SIGNATURE_INVALID"


def test_manifest_pq_signature_enforced():
    key, recs = make_chain(1)
    sm = mc.build_manifest(key, recs[0], "Pacific Rim Auctions", "1.0.0")
    other = mc.derive_keys(SECRET + "other")
    sm["manifest_pq_signature"] = mc.build_manifest(other, recs[0], "Pacific Rim Auctions", "1.0.0")["manifest_pq_signature"]
    assert mc.verify_manifest(mc.public_keys_of(key), sm) is False


def test_chain_verifies_offline_from_published_public_keys_only():
    key, recs = make_chain(3)
    offline = mc.public_keys_from_b64(mc.public_key_b64(key.ed), mc.pq_public_key_b64(key))
    assert mc.verify_chain(recs, offline).status == "VERIFIED"
    recs[2]["payload"]["amount_minor"] = 7
    assert mc.verify_chain(recs, offline).status == "INTEGRITY_FAILURE"


def test_slice_of_chain_verifies_with_start_hash():
    key, recs = make_chain(5)
    sliced = recs[2:]
    r = mc.verify_chain(sliced, mc.public_keys_of(key),
                        start_previous_hash=recs[1]["event_hash"], start_sequence=3)
    assert r.status == "VERIFIED" and r.checked == 3
