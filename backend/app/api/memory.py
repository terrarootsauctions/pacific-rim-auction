from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.memory import MemoryRecord, MemoryVerification
from app.models.user import User
from app.services import memory_core as mc
from app.services import memory_lock

router = APIRouter(prefix="/memory", tags=["memory-lock"])


class ArchiveConfirmation(BaseModel):
    """Entered ONLY after a real physical archive provider has confirmed the
    archive. Nothing here is ever created speculatively."""
    archive_provider: str = Field(min_length=1, max_length=200)
    quartz_archive_id: str = Field(min_length=1, max_length=200)
    archive_timestamp: str = Field(min_length=1, max_length=64)
    package_hash: str = Field(min_length=64, max_length=64)
    verification_status: str = Field(min_length=1, max_length=64)
    chain_of_custody: Optional[str] = None
    archive_location: Optional[str] = None
    certificate_reference: Optional[str] = None


def _summary(row: MemoryRecord) -> dict:
    return {
        "sequence": row.sequence,
        "event_type": row.event_type,
        "event_id": row.event_id,
        "auction_id": row.auction_id,
        "lot_id": row.lot_id,
        "bid_id": row.bid_id,
        "occurred_at": row.occurred_at,
        "event_hash": row.event_hash,
    }


@router.get("/public-key")
def get_public_key():
    """Public information, safe to share: anyone can verify a chain with these."""
    keys = memory_lock._keys()
    return {
        "system": memory_lock.settings.system_identity,
        "key_version": memory_lock.settings.memory_key_version,
        "ed25519": mc.public_key_b64(keys.ed),
        "ed25519_fingerprint": mc.public_key_fingerprint(keys.ed),
        "ml_dsa_65": mc.pq_public_key_b64(keys),
        "note": "Records are signed by BOTH keys; both must verify.",
    }


@router.get("/records")
def list_records(
    after_sequence: int = 0,
    limit: int = 50,
    event_type: Optional[str] = None,
    auction_id: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(MemoryRecord).filter(MemoryRecord.sequence > after_sequence)
    if event_type:
        q = q.filter(MemoryRecord.event_type == event_type)
    if auction_id:
        q = q.filter(MemoryRecord.auction_id == auction_id)
    rows = q.order_by(MemoryRecord.sequence).limit(max(1, min(limit, 200))).all()
    return [_summary(r) for r in rows]


@router.get("/records/{sequence}")
def get_record(sequence: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = memory_lock.get_row(db, sequence)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return {**memory_lock.row_to_dict(row), "archive": memory_lock.archive_info(db, sequence)}


@router.get("/records/{sequence}/manifest")
def get_manifest(sequence: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    manifest = memory_lock.manifest_for(db, sequence)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return manifest


@router.get("/records/{sequence}/provenance")
def get_provenance(sequence: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = memory_lock.get_row(db, sequence)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory record not found")
    prev = memory_lock.get_row(db, sequence - 1) if sequence > 1 else None
    nxt = memory_lock.get_row(db, sequence + 1)
    record = memory_lock.row_to_dict(row)
    # Verify just this record's own hashes and both signatures against its stored predecessor link.
    single = mc.verify_chain(
        [record], memory_lock.public_keys(),
        start_previous_hash=row.previous_hash, start_sequence=sequence,
    )
    return {
        "sequence": sequence,
        "event_hash": row.event_hash,
        "previous_hash": row.previous_hash,
        "links_to_previous_record": bool(prev and prev.event_hash == row.previous_hash)
        if sequence > 1 else row.previous_hash == mc.GENESIS_HASH,
        "next_record_links_back": bool(nxt and nxt.previous_hash == row.event_hash) if nxt else None,
        "own_integrity": single.status,
        "own_integrity_failure": single.failure_reason,
        "archive": memory_lock.archive_info(db, sequence),
    }


@router.get("/records/{sequence}/archive-package")
def get_archive_package(sequence: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """The package to hand to a physical archival provider. Generating this
    does NOT mean anything has been archived."""
    package = memory_lock.archive_package(db, sequence)
    if package is None:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return package


@router.post("/records/{sequence}/archive-confirmation", status_code=201)
def confirm_archive(
    sequence: int,
    body: ArchiveConfirmation,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        arc = memory_lock.confirm_archive(
            db, sequence,
            provider=body.archive_provider,
            archive_id=body.quartz_archive_id,
            archive_timestamp=body.archive_timestamp,
            package_hash=body.package_hash,
            verification_status=body.verification_status,
            recorded_by=admin.id,
            chain_of_custody=body.chain_of_custody,
            archive_location=body.archive_location,
            certificate_reference=body.certificate_reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return memory_lock.archive_info(db, arc.sequence)


@router.get("/verify")
def verify_now(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Recompute the entire chain. VERIFIED only if every record passes."""
    return memory_lock.verify_all(db, trigger="manual")


@router.get("/verifications")
def list_verifications(limit: int = 50, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (
        db.query(MemoryVerification)
        .order_by(MemoryVerification.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": r.id, "status": r.status, "records_checked": r.records_checked,
            "first_failure_sequence": r.first_failure_sequence,
            "failure_reason": r.failure_reason, "trigger": r.trigger,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
        }
        for r in rows
    ]


@router.get("/export")
def export_bundle(
    from_sequence: int = 1,
    limit: int = 1000,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """A portable backup slice that can be verified offline with
    scripts/verify_memory_export.py. Keep copies off this server."""
    return memory_lock.export_bundle(db, max(1, from_sequence), limit)
