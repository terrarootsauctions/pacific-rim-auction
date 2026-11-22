"""
Import every model here so Base.metadata knows about all tables
when create_all() is called.
"""
from app.models.user import User  # noqa: F401
from app.models.asset import Asset  # noqa: F401
from app.models.listing import Listing, Inspection  # noqa: F401
from app.models.bid import Bid  # noqa: F401
from app.models.claim_intake import ClaimIntake  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.jurisdiction_node import JurisdictionNode  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.precedent_log import PrecedentLog  # noqa: F401
from app.models.ledger import BankEvent, LedgerEntry, SettlementDestination  # noqa: F401
from app.models.memory import MemoryArchive, MemoryChainHead, MemoryRecord, MemoryVerification  # noqa: F401
from app.models.algorithm import AlgorithmParameter  # noqa: F401
