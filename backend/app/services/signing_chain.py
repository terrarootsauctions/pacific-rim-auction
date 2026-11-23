"""
Owner authorization signing chain (PURE, no database, standard library only).

Why this exists: Pacific Rim Auctions never owns the unclaimed assets it
surfaces. Before an asset is verified or listed, the legal owner (or their
heirs or authorized representative) signs an authorization agreement. This
module keeps the tamper-evident evidence for that signing: an append-only
list of events where every event's SHA-256 hash covers the previous event's
hash. Changing any past event breaks every hash after it.

What this is not: a legal e-signature service. It records and proves the
sequence of events (document sent, viewed, consent given, signed). Whether a
given signature is legally valid in a given country is decided by the
jurisdiction review (attorney sign-off per node), not by this code.

All functions are pure and deterministic given their inputs, so they can be
tested without a database or network.
"""
import hashlib
import json
from typing import Dict, List, Optional, Tuple

GENESIS_HASH = "0" * 64

EVENT_DOCUMENT_CREATED = "document_created"
EVENT_SENT = "sent"
EVENT_VIEWED = "viewed"
EVENT_CONSENT_GIVEN = "consent_given"
EVENT_SIGNED = "signed"
EVENT_DECLINED = "declined"
EVENT_VOIDED = "voided"

VALID_EVENT_TYPES = frozenset(
    {
        EVENT_DOCUMENT_CREATED,
        EVENT_SENT,
        EVENT_VIEWED,
        EVENT_CONSENT_GIVEN,
        EVENT_SIGNED,
        EVENT_DECLINED,
        EVENT_VOIDED,
    }
)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Dict) -> bytes:
    """Stable serialization: sorted keys, no whitespace, UTF-8. The same
    event always produces the same bytes, on any machine."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_event_hash(prev_hash: str, body: Dict) -> str:
    return sha256_hex(prev_hash.encode("ascii") + canonical_json(body))


def new_event(
    chain: List[Dict],
    event_type: str,
    actor: str,
    occurred_at: str,
    document_sha256: str,
    detail: Optional[Dict] = None,
) -> Dict:
    """Build the next event for `chain` and return it (does not mutate the
    chain; the caller appends and stores it). `occurred_at` is an ISO 8601
    UTC string supplied by the caller so this function stays deterministic.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type!r}")
    if not actor:
        raise ValueError("Every event needs an actor")
    if len(document_sha256) != 64:
        raise ValueError("document_sha256 must be a 64-character SHA-256 hex digest")
    if chain and chain[0]["document_sha256"] != document_sha256:
        raise ValueError("Event is for a different document than the chain it joins")
    if chain and chain[-1]["event_type"] in (EVENT_SIGNED, EVENT_DECLINED, EVENT_VOIDED):
        raise ValueError(f"Chain is closed by a {chain[-1]['event_type']} event")
    if event_type == EVENT_SIGNED and not any(e["event_type"] == EVENT_CONSENT_GIVEN for e in chain):
        raise ValueError("A signature requires an earlier consent_given event")

    prev_hash = chain[-1]["event_hash"] if chain else GENESIS_HASH
    body = {
        "index": len(chain),
        "event_type": event_type,
        "actor": actor,
        "occurred_at": occurred_at,
        "document_sha256": document_sha256,
        "detail": detail or {},
        "prev_hash": prev_hash,
    }
    return {**body, "event_hash": compute_event_hash(prev_hash, body)}


def verify_chain(chain: List[Dict]) -> Tuple[bool, Optional[int]]:
    """Recompute every hash from the stored fields. Returns (True, None) if
    the chain is intact, or (False, index_of_first_bad_event)."""
    prev_hash = GENESIS_HASH
    document = None
    for i, event in enumerate(chain):
        try:
            body = {k: event[k] for k in (
                "index", "event_type", "actor", "occurred_at",
                "document_sha256", "detail", "prev_hash",
            )}
            if event["index"] != i or event["prev_hash"] != prev_hash:
                return False, i
            if event["event_type"] not in VALID_EVENT_TYPES:
                return False, i
            if document is None:
                document = event["document_sha256"]
            elif event["document_sha256"] != document:
                return False, i
            if compute_event_hash(prev_hash, body) != event["event_hash"]:
                return False, i
        except KeyError:
            return False, i
        prev_hash = event["event_hash"]
    return True, None


def is_authorized(chain: List[Dict], document_sha256: str) -> bool:
    """True only if the chain is intact, belongs to this exact document, and
    ends in a signed event. This is the check a listing must pass."""
    if not chain:
        return False
    ok, _ = verify_chain(chain)
    if not ok:
        return False
    return chain[0]["document_sha256"] == document_sha256 and chain[-1]["event_type"] == EVENT_SIGNED


def completion_certificate(chain: List[Dict]) -> Dict:
    """Stand-alone summary of a finished signing, with the final hash so it
    can be checked against the full evidence export later."""
    ok, bad_index = verify_chain(chain)
    if not chain:
        raise ValueError("Cannot certify an empty chain")
    return {
        "document_sha256": chain[0]["document_sha256"],
        "event_count": len(chain),
        "chain_intact": ok,
        "first_bad_index": bad_index,
        "final_event_type": chain[-1]["event_type"],
        "final_hash": chain[-1]["event_hash"],
        "signed": ok and chain[-1]["event_type"] == EVENT_SIGNED,
        "signed_by": chain[-1]["actor"] if chain[-1]["event_type"] == EVENT_SIGNED else None,
        "signed_at": chain[-1]["occurred_at"] if chain[-1]["event_type"] == EVENT_SIGNED else None,
    }
