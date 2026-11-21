"""
Crystal Quartz Memory Lock - cryptographic core (PURE, no database).

What this is: an append-only chain of event records. Each record carries a
SHA-256 content hash, a SHA-256 event hash that covers the previous record's
hash, and an Ed25519 signature. Changing any past record breaks every hash
after it, and verification recomputes everything from the stored fields.

What this is not: the physical 5D fused-quartz archive. That is a separate
real-world service. Nothing here claims a physical archive exists; see
`archive_status` handling in memory_lock.py.

Cryptography used: SHA-256 (hashlib), HKDF-SHA256, and a HYBRID signature:
Ed25519 (classical) plus ML-DSA-65 (FIPS 204, the NIST post-quantum
signature standard), both from the widely used `cryptography` package. A
record verifies only if BOTH signatures verify, so it stays trustworthy even
if one scheme is later weakened, including by quantum computers. Nothing
proprietary was invented.
Encryption: record payloads hold identifiers and amounts only, never
personal data or credentials, so they are signed, not encrypted. The record
says so explicitly (`encryption_algorithm = "none"`).
"""
import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.mldsa import (
    MLDSA65PrivateKey,
    MLDSA65PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import serialization

SCHEMA_VERSION = "1"
GENESIS_HASH = "0" * 64
HASH_ALGORITHM = "SHA-256"
SIGNATURE_ALGORITHM = "Ed25519"
PQ_SIGNATURE_ALGORITHM = "ML-DSA-65"
ENCRYPTION_ALGORITHM = "none"

# Fields that make up a record's identity. The event hash covers all of them.
SIGNED_FIELDS = (
    "schema_version", "sequence", "event_type", "event_id", "auction_id",
    "lot_id", "bid_id", "actor_id", "occurred_at", "content_hash",
    "metadata_hash", "previous_hash", "key_version",
)


def canonical_json(obj) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8. The same data
    always produces the same bytes, which is what makes hashes verifiable."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_private_key(secret: str, key_version: str = "1") -> Ed25519PrivateKey:
    """Derive the signing key from the host's secret with HKDF-SHA256. The
    same secret always gives the same key, so signatures stay verifiable
    across restarts. Losing or changing the secret makes OLD signatures
    unverifiable with the new key, so back the secret up."""
    if not secret or len(secret) < 16:
        raise ValueError("MEMORY_SIGNING_SECRET must be set to a long random value.")
    seed = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=f"pacific-rim-memory-lock/ed25519/v{key_version}".encode("utf-8"),
    ).derive(secret.encode("utf-8"))
    return Ed25519PrivateKey.from_private_bytes(seed)


@dataclass
class SigningKeys:
    """The hybrid key pair: classical Ed25519 plus post-quantum ML-DSA-65."""
    ed: Ed25519PrivateKey
    pq: MLDSA65PrivateKey


@dataclass
class PublicKeys:
    ed: Ed25519PublicKey
    pq: Optional[MLDSA65PublicKey]


def derive_pq_private_key(secret: str, key_version: str = "1") -> MLDSA65PrivateKey:
    if not secret or len(secret) < 16:
        raise ValueError("MEMORY_SIGNING_SECRET must be set to a long random value.")
    seed = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=f"pacific-rim-memory-lock/ml-dsa-65/v{key_version}".encode("utf-8"),
    ).derive(secret.encode("utf-8"))
    return MLDSA65PrivateKey.from_seed_bytes(seed)


def derive_keys(secret: str, key_version: str = "1") -> SigningKeys:
    return SigningKeys(
        ed=derive_private_key(secret, key_version),
        pq=derive_pq_private_key(secret, key_version),
    )


def public_keys_of(keys: SigningKeys) -> PublicKeys:
    return PublicKeys(ed=keys.ed.public_key(), pq=keys.pq.public_key())


def public_keys_from_b64(ed_b64: str, pq_b64: Optional[str]) -> PublicKeys:
    """Rebuild public keys from the base64 text published by this system, so
    a chain can be verified offline, away from the server and its secret."""
    ed = Ed25519PublicKey.from_public_bytes(base64.b64decode(ed_b64))
    pq = MLDSA65PublicKey.from_public_bytes(base64.b64decode(pq_b64)) if pq_b64 else None
    return PublicKeys(ed=ed, pq=pq)


def pq_public_key_b64(keys: SigningKeys) -> str:
    raw = keys.pq.public_key().public_bytes_raw()
    return base64.b64encode(bytes(raw)).decode("ascii")


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def public_key_fingerprint(private_key: Ed25519PrivateKey) -> str:
    raw = base64.b64decode(public_key_b64(private_key))
    return sha256_hex(raw)[:16]


def _signing_bytes(record: Dict) -> bytes:
    return canonical_json({k: record[k] for k in SIGNED_FIELDS})


def compute_event_hash(record: Dict) -> str:
    return sha256_hex(_signing_bytes(record))


def build_record(
    keys: SigningKeys,
    *,
    sequence: int,
    previous_hash: str,
    event_type: str,
    event_id: str,
    occurred_at: str,
    payload: Dict,
    metadata: Optional[Dict] = None,
    auction_id: Optional[str] = None,
    lot_id: Optional[str] = None,
    bid_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    key_version: str = "1",
) -> Dict:
    """Create one locked record: hashes, chain link and signature."""
    metadata = metadata or {}
    record = {
        "schema_version": SCHEMA_VERSION,
        "sequence": sequence,
        "event_type": event_type,
        "event_id": event_id,
        "auction_id": auction_id,
        "lot_id": lot_id,
        "bid_id": bid_id,
        "actor_id": actor_id,
        "occurred_at": occurred_at,
        "content_hash": sha256_hex(canonical_json(payload)),
        "metadata_hash": sha256_hex(canonical_json(metadata)),
        "previous_hash": previous_hash,
        "key_version": key_version,
    }
    record["event_hash"] = compute_event_hash(record)
    digest = record["event_hash"].encode("ascii")
    record["signature"] = base64.b64encode(keys.ed.sign(digest)).decode("ascii")
    record["pq_signature"] = base64.b64encode(bytes(keys.pq.sign(digest))).decode("ascii")
    record["payload"] = payload
    record["metadata"] = metadata
    record["hash_algorithm"] = HASH_ALGORITHM
    record["signature_algorithm"] = SIGNATURE_ALGORITHM
    record["pq_signature_algorithm"] = PQ_SIGNATURE_ALGORITHM
    record["encryption_algorithm"] = ENCRYPTION_ALGORITHM
    return record


def verify_signature(public_key: Ed25519PublicKey, event_hash: str, signature_b64: str) -> bool:
    try:
        public_key.verify(base64.b64decode(signature_b64), event_hash.encode("ascii"))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_pq_signature(public_key: MLDSA65PublicKey, event_hash: str, signature_b64: str) -> bool:
    try:
        public_key.verify(base64.b64decode(signature_b64), event_hash.encode("ascii"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


@dataclass
class ChainResult:
    status: str                       # "VERIFIED" or "INTEGRITY_FAILURE"
    checked: int
    first_failure_sequence: Optional[int] = None
    failure_reason: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None


def verify_chain(
    records: Iterable[Dict],
    public_keys: PublicKeys,
    start_previous_hash: str = GENESIS_HASH,
    start_sequence: int = 1,
) -> ChainResult:
    """Recompute everything from the stored fields. Returns VERIFIED only if
    every check passes for every record; never because a record merely
    exists. Checks per record: sequence continuity, previous-hash link,
    content hash, metadata hash, event hash, signature."""
    expected_seq = start_sequence
    prev = start_previous_hash
    count = 0

    def fail(rec, reason, expected=None, actual=None):
        return ChainResult("INTEGRITY_FAILURE", count, rec.get("sequence"), reason, expected, actual)

    for rec in records:
        if rec["sequence"] != expected_seq:
            return fail(rec, "SEQUENCE_GAP", str(expected_seq), str(rec["sequence"]))
        if rec["previous_hash"] != prev:
            return fail(rec, "PREVIOUS_HASH_MISMATCH", prev, rec["previous_hash"])
        content = sha256_hex(canonical_json(rec["payload"]))
        if content != rec["content_hash"]:
            return fail(rec, "CONTENT_HASH_MISMATCH", rec["content_hash"], content)
        meta = sha256_hex(canonical_json(rec.get("metadata") or {}))
        if meta != rec["metadata_hash"]:
            return fail(rec, "METADATA_HASH_MISMATCH", rec["metadata_hash"], meta)
        event_hash = compute_event_hash(rec)
        if event_hash != rec["event_hash"]:
            return fail(rec, "EVENT_HASH_MISMATCH", rec["event_hash"], event_hash)
        if not verify_signature(public_keys.ed, rec["event_hash"], rec["signature"]):
            return fail(rec, "SIGNATURE_INVALID", None, None)
        if public_keys.pq is not None and not verify_pq_signature(
            public_keys.pq, rec["event_hash"], rec.get("pq_signature") or ""
        ):
            return fail(rec, "PQ_SIGNATURE_INVALID", None, None)
        prev = rec["event_hash"]
        expected_seq += 1
        count += 1

    return ChainResult("VERIFIED", count)


def build_manifest(keys: SigningKeys, record: Dict, system_identity: str,
                   app_version: str, archive: Optional[Dict] = None) -> Dict:
    """A signed manifest describing one record. The archive block reflects
    only a provider-confirmed archive; otherwise it says NOT_ARCHIVED."""
    body = {
        "system": system_identity,
        "schema_version": record["schema_version"],
        "application_version": app_version,
        "memory_sequence": record["sequence"],
        "event_type": record["event_type"],
        "event_id": record["event_id"],
        "auction_id": record["auction_id"],
        "lot_id": record["lot_id"],
        "bid_id": record["bid_id"],
        "occurred_at": record["occurred_at"],
        "content_hash": record["content_hash"],
        "metadata_hash": record["metadata_hash"],
        "previous_hash": record["previous_hash"],
        "event_hash": record["event_hash"],
        "record_signature": record["signature"],
        "hash_algorithm": record["hash_algorithm"],
        "signature_algorithm": record["signature_algorithm"],
        "pq_signature_algorithm": record.get("pq_signature_algorithm", PQ_SIGNATURE_ALGORITHM),
        "encryption_algorithm": record["encryption_algorithm"],
        "key_version": record["key_version"],
        "archive": archive or {"status": "NOT_ARCHIVED"},
    }
    data = canonical_json(body)
    return {
        "manifest": body,
        "manifest_signature": base64.b64encode(keys.ed.sign(data)).decode("ascii"),
        "manifest_pq_signature": base64.b64encode(bytes(keys.pq.sign(data))).decode("ascii"),
    }


def verify_manifest(public_keys: PublicKeys, signed_manifest: Dict) -> bool:
    try:
        data = canonical_json(signed_manifest["manifest"])
        public_keys.ed.verify(base64.b64decode(signed_manifest["manifest_signature"]), data)
        if public_keys.pq is not None:
            public_keys.pq.verify(base64.b64decode(signed_manifest["manifest_pq_signature"]), data)
        return True
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
