"""
Crystal Quartz Memory Lock - database layer.

Every critical production event is captured into the SAME database
transaction as the business change it describes. So an accepted bid and its
memory record are saved together or not at all: an accepted event can never
silently disappear because the memory layer failed (the whole request fails
and the client retries safely, because bids are idempotent).

The chain tip row is locked while a record is appended, so two writers can
never fork the chain. Locked records are only ever inserted, never updated.

HONEST LIMITS:
  - This is a cryptographic database chain, NOT the physical 5D quartz archive.
    A record shows archive status NOT_ARCHIVED until a real provider
    confirmation is entered (see confirm_archive).
  - One global chain means appends are serialized. That is the price of a
    single provable history; revisit sharding only if volume demands it.
"""
import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Dict, Iterator, List, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.memory import MemoryArchive, MemoryChainHead, MemoryRecord, MemoryVerification
from app.services import memory_core as mc

settings = get_settings()


class EventType:
    AUCTION_CREATED = "AUCTION_CREATED"
    AUCTION_UPDATED = "AUCTION_UPDATED"
    AUCTION_OPENED = "AUCTION_OPENED"
    LOT_CREATED = "LOT_CREATED"
    LOT_UPDATED = "LOT_UPDATED"
    BID_SUBMITTED = "BID_SUBMITTED"
    BID_ACCEPTED = "BID_ACCEPTED"
    BID_REJECTED = "BID_REJECTED"
    AUCTION_EXTENDED = "AUCTION_EXTENDED"
    AUCTION_CLOSED = "AUCTION_CLOSED"
    WINNER_CONFIRMED = "WINNER_CONFIRMED"
    PAYMENT_STATUS_CHANGED = "PAYMENT_STATUS_CHANGED"
    SETTLEMENT_STATUS_CHANGED = "SETTLEMENT_STATUS_CHANGED"
    ADMINISTRATIVE_ACTION = "ADMINISTRATIVE_ACTION"
    SECURITY_EVENT = "SECURITY_EVENT"
    COMPLIANCE_EVENT = "COMPLIANCE_EVENT"
    ALGORITHM_CHANGE = "ALGORITHM_CHANGE"
    SYSTEM_EVENT = "SYSTEM_EVENT"
    MEMORY_INTEGRITY_FAILURE = "MEMORY_INTEGRITY_FAILURE"
    MEMORY_VERIFICATION = "MEMORY_VERIFICATION"
    ARCHIVE_CONFIRMED = "ARCHIVE_CONFIRMED"


@lru_cache(maxsize=1)
def _keys() -> mc.SigningKeys:
    return mc.derive_keys(settings.memory_signing_secret, settings.memory_key_version)


def public_keys() -> mc.PublicKeys:
    return mc.public_keys_of(_keys())


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ensure_chain_head(db: Session) -> MemoryChainHead:
    head = db.get(MemoryChainHead, 1)
    if head is None:
        head = MemoryChainHead(id=1, last_sequence=0, last_hash=mc.GENESIS_HASH)
        db.add(head)
        db.commit()
    return head


def capture(
    db: Session,
    event_type: str,
    payload: Dict,
    *,
    auction_id: Optional[str] = None,
    lot_id: Optional[str] = None,
    bid_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    event_id: Optional[str] = None,
) -> MemoryRecord:
    """Append one locked record. Flushes but does NOT commit: the caller's
    commit saves the business change and its memory record together."""
    head = (
        db.query(MemoryChainHead).filter(MemoryChainHead.id == 1).with_for_update().first()
    )
    if head is None:
        head = MemoryChainHead(id=1, last_sequence=0, last_hash=mc.GENESIS_HASH)
        db.add(head)
        db.flush()

    sequence = head.last_sequence + 1
    rec = mc.build_record(
        _keys(),
        sequence=sequence,
        previous_hash=head.last_hash,
        event_type=event_type,
        event_id=event_id or str(uuid.uuid4()),
        occurred_at=now_iso(),
        payload=payload,
        metadata=metadata,
        auction_id=auction_id,
        lot_id=lot_id,
        bid_id=bid_id,
        actor_id=actor_id,
        key_version=settings.memory_key_version,
    )
    row = MemoryRecord(
        sequence=rec["sequence"],
        schema_version=rec["schema_version"],
        event_type=rec["event_type"],
        event_id=rec["event_id"],
        auction_id=rec["auction_id"],
        lot_id=rec["lot_id"],
        bid_id=rec["bid_id"],
        actor_id=rec["actor_id"],
        occurred_at=rec["occurred_at"],
        content_hash=rec["content_hash"],
        metadata_hash=rec["metadata_hash"],
        previous_hash=rec["previous_hash"],
        event_hash=rec["event_hash"],
        signature=rec["signature"],
        pq_signature=rec["pq_signature"],
        pq_signature_algorithm=rec["pq_signature_algorithm"],
        key_version=rec["key_version"],
        hash_algorithm=rec["hash_algorithm"],
        signature_algorithm=rec["signature_algorithm"],
        encryption_algorithm=rec["encryption_algorithm"],
        payload_json=mc.canonical_json(rec["payload"]).decode("utf-8"),
        metadata_json=mc.canonical_json(rec["metadata"]).decode("utf-8"),
    )
    db.add(row)
    head.last_sequence = sequence
    head.last_hash = rec["event_hash"]
    db.flush()
    return row


def row_to_dict(row: MemoryRecord) -> Dict:
    return {
        "schema_version": row.schema_version,
        "sequence": row.sequence,
        "event_type": row.event_type,
        "event_id": row.event_id,
        "auction_id": row.auction_id,
        "lot_id": row.lot_id,
        "bid_id": row.bid_id,
        "actor_id": row.actor_id,
        "occurred_at": row.occurred_at,
        "content_hash": row.content_hash,
        "metadata_hash": row.metadata_hash,
        "previous_hash": row.previous_hash,
        "event_hash": row.event_hash,
        "signature": row.signature,
        "pq_signature": row.pq_signature,
        "pq_signature_algorithm": row.pq_signature_algorithm,
        "key_version": row.key_version,
        "hash_algorithm": row.hash_algorithm,
        "signature_algorithm": row.signature_algorithm,
        "encryption_algorithm": row.encryption_algorithm,
        "payload": json.loads(row.payload_json),
        "metadata": json.loads(row.metadata_json),
    }


def _iter_records(db: Session, batch: int = 500) -> Iterator[Dict]:
    last = 0
    while True:
        rows = (
            db.query(MemoryRecord)
            .filter(MemoryRecord.sequence > last)
            .order_by(MemoryRecord.sequence)
            .limit(batch)
            .all()
        )
        if not rows:
            return
        for row in rows:
            yield row_to_dict(row)
        last = rows[-1].sequence


def verify_all(db: Session, trigger: str = "manual", record_failure: bool = True) -> Dict:
    """Recompute the whole chain from stored fields. Returns VERIFIED only if
    every record and the chain tip check out; never because a row merely
    exists. Every run is stored as its own verification row. A failure also
    appends a MEMORY_INTEGRITY_FAILURE event; the damaged evidence is left
    exactly as found."""
    result = mc.verify_chain(_iter_records(db), public_keys())
    status = result.status
    failure_reason = result.failure_reason
    expected, actual = result.expected, result.actual
    first_failure = result.first_failure_sequence

    if status == "VERIFIED":
        head = db.get(MemoryChainHead, 1)
        last_row = db.query(MemoryRecord).order_by(MemoryRecord.sequence.desc()).first()
        head_seq = head.last_sequence if head else 0
        head_hash = head.last_hash if head else mc.GENESIS_HASH
        last_seq = last_row.sequence if last_row else 0
        last_hash = last_row.event_hash if last_row else mc.GENESIS_HASH
        if head_seq != last_seq or head_hash != last_hash:
            status = "INTEGRITY_FAILURE"
            failure_reason = "CHAIN_TIP_MISMATCH"
            expected, actual = f"{head_seq}:{head_hash}", f"{last_seq}:{last_hash}"
            first_failure = last_seq

    row = MemoryVerification(
        status=status,
        records_checked=result.checked,
        first_failure_sequence=first_failure,
        failure_reason=failure_reason,
        expected=expected,
        actual=actual,
        trigger=trigger,
    )
    db.add(row)
    if status != "VERIFIED" and record_failure:
        capture(
            db,
            EventType.MEMORY_INTEGRITY_FAILURE,
            {
                "first_failure_sequence": first_failure,
                "failure_reason": failure_reason,
                "expected": expected,
                "actual": actual,
                "trigger": trigger,
            },
            metadata={"note": "Affected evidence preserved; recover only from a verified copy."},
        )
    db.commit()
    return {
        "status": status,
        "records_checked": result.checked,
        "first_failure_sequence": first_failure,
        "failure_reason": failure_reason,
        "expected": expected,
        "actual": actual,
        "trigger": trigger,
    }


def get_row(db: Session, sequence: int) -> Optional[MemoryRecord]:
    return db.get(MemoryRecord, sequence)


def archive_info(db: Session, sequence: int) -> Dict:
    arc = (
        db.query(MemoryArchive)
        .filter(MemoryArchive.sequence == sequence)
        .order_by(MemoryArchive.id.desc())
        .first()
    )
    if arc is None:
        return {"status": "NOT_ARCHIVED"}
    return {
        "status": "ARCHIVE_CONFIRMED",
        "archive_provider": arc.archive_provider,
        "quartz_archive_id": arc.archive_id,
        "archive_timestamp": arc.archive_timestamp,
        "package_hash": arc.package_hash,
        "verification_status": arc.verification_status,
        "chain_of_custody": arc.chain_of_custody,
        "archive_location": arc.archive_location,
        "certificate_reference": arc.certificate_reference,
    }


def manifest_for(db: Session, sequence: int, include_archive: bool = True) -> Optional[Dict]:
    row = get_row(db, sequence)
    if row is None:
        return None
    archive = archive_info(db, sequence) if include_archive else None
    return mc.build_manifest(
        _keys(), row_to_dict(row), settings.system_identity, settings.app_version, archive
    )


def archive_package(db: Session, sequence: int) -> Optional[Dict]:
    """Everything a physical archival provider needs: data, manifest, hashes,
    signatures, schema, version, decoding information, provenance, integrity.
    The manifest inside is always the NOT_ARCHIVED form so the package hash
    is stable and the provider can confirm exactly what it stored."""
    row = get_row(db, sequence)
    if row is None:
        return None
    record = row_to_dict(row)
    package = {
        "package_format": "pacific-rim-memory-archive/1",
        "data": record,
        "manifest": mc.build_manifest(
            _keys(), record, settings.system_identity, settings.app_version, None
        ),
        "hashes": {
            "content_hash": record["content_hash"],
            "metadata_hash": record["metadata_hash"],
            "previous_hash": record["previous_hash"],
            "event_hash": record["event_hash"],
        },
        "signatures": {"ed25519": record["signature"], "ml_dsa_65": record["pq_signature"]},
        "public_keys": {
            "ed25519": mc.public_key_b64(_keys().ed),
            "ml_dsa_65": mc.pq_public_key_b64(_keys()),
        },
        "schema_version": record["schema_version"],
        "application_version": settings.app_version,
        "decoding_information": (
            "Records are UTF-8 canonical JSON (sorted keys, no whitespace). Hashes are SHA-256 hex. "
            "event_hash = SHA-256 of the canonical JSON of the signed fields. Signatures are base64 "
            "over the ASCII event_hash: Ed25519 and ML-DSA-65 (FIPS 204). Both must verify."
        ),
        "provenance": {
            "system": settings.system_identity,
            "sequence": record["sequence"],
            "previous_hash": record["previous_hash"],
        },
    }
    package["package_hash"] = mc.sha256_hex(mc.canonical_json(package))
    return package


def confirm_archive(
    db: Session,
    sequence: int,
    *,
    provider: str,
    archive_id: str,
    archive_timestamp: str,
    package_hash: str,
    verification_status: str,
    recorded_by: str,
    chain_of_custody: Optional[str] = None,
    archive_location: Optional[str] = None,
    certificate_reference: Optional[str] = None,
) -> MemoryArchive:
    """Record a PROVIDER-CONFIRMED physical archive. Refuses unless the
    provider's package hash equals the package this system produced, so a
    confirmation can only ever describe exactly what we generated."""
    package = archive_package(db, sequence)
    if package is None:
        raise ValueError("No such memory record.")
    if package_hash != package["package_hash"]:
        raise ValueError("Provider package hash does not match the package generated for this record.")

    arc = MemoryArchive(
        sequence=sequence,
        archive_provider=provider,
        archive_id=archive_id,
        archive_timestamp=archive_timestamp,
        package_hash=package_hash,
        verification_status=verification_status,
        chain_of_custody=chain_of_custody,
        archive_location=archive_location,
        certificate_reference=certificate_reference,
        recorded_by=recorded_by,
    )
    db.add(arc)
    capture(
        db,
        EventType.ARCHIVE_CONFIRMED,
        {
            "archived_sequence": sequence,
            "archive_provider": provider,
            "quartz_archive_id": archive_id,
            "package_hash": package_hash,
        },
        actor_id=recorded_by,
    )
    db.commit()
    db.refresh(arc)
    return arc


def export_bundle(db: Session, from_sequence: int = 1, limit: int = 1000) -> Dict:
    """A portable, offline-verifiable backup slice. It carries the public
    keys and the previous hash needed to verify it without this server
    (see scripts/verify_memory_export.py)."""
    limit = max(1, min(limit, 5000))
    rows = (
        db.query(MemoryRecord)
        .filter(MemoryRecord.sequence >= from_sequence)
        .order_by(MemoryRecord.sequence)
        .limit(limit)
        .all()
    )
    prev_hash = mc.GENESIS_HASH
    if from_sequence > 1:
        prev = get_row(db, from_sequence - 1)
        prev_hash = prev.event_hash if prev else mc.GENESIS_HASH
    return {
        "bundle_format": "pacific-rim-memory-export/1",
        "system": settings.system_identity,
        "from_sequence": from_sequence,
        "start_previous_hash": prev_hash,
        "public_keys": {
            "ed25519": mc.public_key_b64(_keys().ed),
            "ml_dsa_65": mc.pq_public_key_b64(_keys()),
        },
        "records": [row_to_dict(r) for r in rows],
    }
