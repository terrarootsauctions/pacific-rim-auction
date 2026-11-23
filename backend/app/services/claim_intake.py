"""
Claim intake rules (PURE, no database).

Pacific Rim Auctions never owns the unclaimed assets it surfaces. A claim
intake is a request from a person who says they are the owner, an heir, or
an authorized representative of the owner. It moves through identity review
and a signed authorization before anything can be listed.

This module holds the rules only: what an intake may contain, which status
moves are allowed, and what a finder fee may be. The database model and the
API call these functions, so the rules can be tested without either.

Privacy rule: the platform never collects government ID numbers, bank
account numbers or card numbers in an intake. Identity is verified by a
human reviewer, through channels outside this form. Free-text fields that
look like such numbers are refused so they are never stored.
"""
import enum
import re
from typing import Dict, Iterable, Optional, Tuple

from app.services import signing_chain


class Relationship(str, enum.Enum):
    OWNER = "owner"
    HEIR = "heir"
    AUTHORIZED_REPRESENTATIVE = "authorized_representative"


class IntakeStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    IDENTITY_REVIEW = "identity_review"
    AWAITING_SIGNATURE = "awaiting_signature"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# Allowed moves. AUTHORIZED is reachable only through a verified signing
# chain (see advance_status). REJECTED and WITHDRAWN are final.
ALLOWED_TRANSITIONS: Dict[IntakeStatus, frozenset] = {
    IntakeStatus.SUBMITTED: frozenset({IntakeStatus.IDENTITY_REVIEW, IntakeStatus.REJECTED, IntakeStatus.WITHDRAWN}),
    IntakeStatus.IDENTITY_REVIEW: frozenset({IntakeStatus.AWAITING_SIGNATURE, IntakeStatus.REJECTED, IntakeStatus.WITHDRAWN}),
    IntakeStatus.AWAITING_SIGNATURE: frozenset({IntakeStatus.AUTHORIZED, IntakeStatus.REJECTED, IntakeStatus.WITHDRAWN}),
    IntakeStatus.AUTHORIZED: frozenset({IntakeStatus.WITHDRAWN}),
    IntakeStatus.REJECTED: frozenset(),
    IntakeStatus.WITHDRAWN: frozenset(),
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
# 9 or more digits in a row (allowing spaces or dashes between them) looks
# like an ID, account or card number.
_LONG_NUMBER_RE = re.compile(r"(?:\d[\s-]?){9,}")

MAX_TEXT = 4000
MAX_NAME = 200


def looks_like_sensitive_number(text: str) -> bool:
    return bool(_LONG_NUMBER_RE.search(text or ""))


def validate_intake(
    claimant_name: str,
    contact_email: str,
    country: str,
    relationship: str,
    description: Optional[str] = None,
    region: Optional[str] = None,
) -> Dict:
    """Return a cleaned dict, or raise ValueError with a plain message."""
    name = (claimant_name or "").strip()
    email = (contact_email or "").strip().lower()
    country_code = (country or "").strip().upper()
    text = (description or "").strip()
    region_code = (region or "").strip().upper() or None

    if not name or len(name) > MAX_NAME:
        raise ValueError("Enter the claimant's name (up to 200 characters).")
    if not _EMAIL_RE.match(email):
        raise ValueError("Enter a valid contact email address.")
    if not _COUNTRY_RE.match(country_code):
        raise ValueError("Enter the country as a two-letter ISO code, such as US.")
    try:
        rel = Relationship(relationship)
    except ValueError:
        raise ValueError("Relationship must be owner, heir or authorized_representative.")
    if len(text) > MAX_TEXT:
        raise ValueError("Description is too long (limit 4000 characters).")
    for label, value in (("name", name), ("description", text)):
        if looks_like_sensitive_number(value):
            raise ValueError(
                f"The {label} looks like it contains an ID, account or card number. "
                "Remove it. Identity is verified separately and never through this form."
            )
    return {
        "claimant_name": name,
        "contact_email": email,
        "country": country_code,
        "region": region_code,
        "relationship": rel,
        "description": text or None,
    }


def validate_fee(requested_bps: int, legal_cap_bps: Optional[int]) -> int:
    """A finder fee is agreed only within the legal cap that compliance has
    recorded for the jurisdiction. No cap on file means no fee can be agreed
    yet: the platform does not guess what the law allows."""
    if isinstance(requested_bps, bool) or not isinstance(requested_bps, int):
        raise ValueError("Fee must be whole basis points (for example 1000 for 10%).")
    if requested_bps < 0:
        raise ValueError("Fee cannot be negative.")
    if legal_cap_bps is None:
        raise ValueError("No legal fee cap is recorded for this jurisdiction. Compliance must set one first.")
    if requested_bps > legal_cap_bps:
        raise ValueError(f"Fee exceeds the legal cap of {legal_cap_bps} basis points for this jurisdiction.")
    return requested_bps


def advance_status(
    current: IntakeStatus,
    target: IntakeStatus,
    jurisdiction_cleared: bool,
    signing_events: Optional[Iterable[Dict]] = None,
    document_sha256: Optional[str] = None,
) -> Tuple[IntakeStatus, str]:
    """Check one status move. Returns (new_status, reason) or raises
    ValueError. Two gates are enforced here:

    - Leaving identity review for signature needs a jurisdiction that
      compliance has marked ACTIVE (jurisdiction_cleared).
    - AUTHORIZED needs an intact signing chain, ending in a signature, for
      the exact agreement document on file.
    """
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Cannot move from {current.value} to {target.value}.")
    if target == IntakeStatus.AWAITING_SIGNATURE and not jurisdiction_cleared:
        raise ValueError("This jurisdiction has not been cleared by legal review, so no agreement can be sent.")
    if target == IntakeStatus.AUTHORIZED:
        events = list(signing_events or [])
        if not document_sha256 or not signing_chain.is_authorized(events, document_sha256):
            raise ValueError("No intact, completed signature exists for the agreement on file.")
    return target, f"{current.value} -> {target.value}"
