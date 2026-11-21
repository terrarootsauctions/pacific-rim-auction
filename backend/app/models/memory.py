"""
Memory Lock tables. Locked records are only ever INSERTED. Archive
confirmations and verification results live in their own tables so a locked
record is never modified after it is written.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class MemoryChainHead(Base):
    """Single row (id=1) holding the tip of the chain. Locked FOR UPDATE
    while a record is appended, so two writers can never fork the chain."""
    __tablename__ = "memory_chain_head"

    id = Column(Integer, primary_key=True)
    last_sequence = Column(BigInteger, nullable=False, default=0)
    last_hash = Column(String(64), nullable=False)


class MemoryRecord(Base):
    __tablename__ = "memory_records"

    sequence = Column(BigInteger, primary_key=True, autoincrement=False)
    schema_version = Column(String(8), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    event_id = Column(String(64), nullable=False, unique=True)
    auction_id = Column(String, nullable=True, index=True)
    lot_id = Column(String, nullable=True)
    bid_id = Column(String, nullable=True)
    actor_id = Column(String, nullable=True)
    occurred_at = Column(String(40), nullable=False)
    content_hash = Column(String(64), nullable=False)
    metadata_hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64), nullable=False)
    event_hash = Column(String(64), nullable=False, unique=True)
    signature = Column(String, nullable=False)
    pq_signature = Column(Text, nullable=False)
    pq_signature_algorithm = Column(String(16), nullable=False)
    key_version = Column(String(16), nullable=False)
    hash_algorithm = Column(String(16), nullable=False)
    signature_algorithm = Column(String(16), nullable=False)
    encryption_algorithm = Column(String(16), nullable=False)
    payload_json = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MemoryVerification(Base):
    __tablename__ = "memory_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(24), nullable=False)  # VERIFIED | INTEGRITY_FAILURE
    records_checked = Column(BigInteger, nullable=False)
    first_failure_sequence = Column(BigInteger, nullable=True)
    failure_reason = Column(String(64), nullable=True)
    expected = Column(String, nullable=True)
    actual = Column(String, nullable=True)
    trigger = Column(String(32), nullable=False)  # manual | scheduled
    verified_at = Column(DateTime, default=datetime.utcnow, index=True)


class MemoryArchive(Base):
    """A PROVIDER-CONFIRMED physical archive of one record. A row exists only
    after a real confirmation is entered; nothing is ever created speculatively."""
    __tablename__ = "memory_archives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sequence = Column(BigInteger, ForeignKey("memory_records.sequence"), nullable=False, index=True)
    archive_provider = Column(String, nullable=False)
    archive_id = Column(String, nullable=False)
    archive_timestamp = Column(String, nullable=False)
    package_hash = Column(String(64), nullable=False)
    verification_status = Column(String, nullable=False)
    chain_of_custody = Column(Text, nullable=True)
    archive_location = Column(String, nullable=True)
    certificate_reference = Column(String, nullable=True)
    recorded_by = Column(String, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
