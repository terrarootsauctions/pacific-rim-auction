"""
Listing gate (PURE, no database): decides whether an asset may be listed.

Implements the two governing mandates (Do No Harm, Follow the Laws of the
Land) as one automatic check the SI can run with no human in the loop. The
gate acts the moment the required facts exist on record, and refuses
otherwise. It never asks anyone to approve; it reads records.

An asset may be listed only when ALL of these hold:
  1. its jurisdiction has been cleared by legal review (country-by-country
     law is the Follow the Laws mandate),
  2. Do No Harm screening has cleared it (not pending, not flagged),
  3. a lawful basis is on record, one of:
       - owner_authorization: a claim intake in AUTHORIZED status, backed by
         an intact signature chain for the agreement on file,
       - seller_title: the seller holds title to the asset themselves,
       - government_authority: a government sale (tax sale, surplus auction)
         with the authority's reference recorded,
       - court_order: a court-ordered sale with the order's reference recorded.
     Government and court bases need the reference recorded so an attorney
     can verify it; a blank reference does not count.
"""
from typing import Dict, Iterable, List, Optional, Tuple

from app.services import signing_chain

BASIS_OWNER_AUTHORIZATION = "owner_authorization"
BASIS_SELLER_TITLE = "seller_title"
BASIS_GOVERNMENT_AUTHORITY = "government_authority"
BASIS_COURT_ORDER = "court_order"

BASES_NEEDING_REFERENCE = frozenset({BASIS_GOVERNMENT_AUTHORITY, BASIS_COURT_ORDER})
VALID_BASES = frozenset(
    {BASIS_OWNER_AUTHORIZATION, BASIS_SELLER_TITLE, BASIS_GOVERNMENT_AUTHORITY, BASIS_COURT_ORDER}
)


def check_listing(
    jurisdiction_cleared: bool,
    do_no_harm_status: str,
    basis: Optional[str],
    reference: Optional[str] = None,
    signing_events: Optional[Iterable[Dict]] = None,
    document_sha256: Optional[str] = None,
    seller_holds_title: bool = False,
) -> Tuple[bool, List[str]]:
    """Return (allowed, reasons). `reasons` lists every failed condition, so
    the SI can log exactly what is missing and act when it appears."""
    reasons: List[str] = []

    if not jurisdiction_cleared:
        reasons.append("Jurisdiction has not been cleared by legal review.")
    if do_no_harm_status != "cleared":
        reasons.append(f"Do No Harm screening is '{do_no_harm_status}', not 'cleared'.")

    if basis not in VALID_BASES:
        reasons.append("No lawful basis is on record.")
    elif basis == BASIS_OWNER_AUTHORIZATION:
        events = list(signing_events or [])
        if not document_sha256 or not signing_chain.is_authorized(events, document_sha256):
            reasons.append("No intact, completed owner signature exists for the agreement on file.")
    elif basis == BASIS_SELLER_TITLE:
        if not seller_holds_title:
            reasons.append("Seller title has not been confirmed.")
    elif basis in BASES_NEEDING_REFERENCE:
        if not (reference or "").strip():
            reasons.append(f"The {basis.replace('_', ' ')} reference is not recorded.")

    return (not reasons), reasons


RECORDABLE_BASES = frozenset({BASIS_SELLER_TITLE, BASIS_GOVERNMENT_AUTHORITY, BASIS_COURT_ORDER})


def validate_basis_record(basis: str, reference: Optional[str]) -> str:
    """Check a lawful-basis record before it is stored. Owner authorization
    is never recorded by hand: it is derived from a claim intake that has a
    verified signature chain. Returns the cleaned reference."""
    if basis not in RECORDABLE_BASES:
        raise ValueError(
            "Basis must be seller_title, government_authority or court_order. "
            "Owner authorization comes from a signed claim intake, not a manual record."
        )
    ref = (reference or "").strip()
    if basis in BASES_NEEDING_REFERENCE and not ref:
        raise ValueError(f"A {basis.replace('_', ' ')} needs its reference recorded so legal review can verify it.")
    return ref


def check_any(
    jurisdiction_cleared: bool,
    do_no_harm_status: str,
    candidates: Iterable[Dict],
) -> Tuple[bool, List[str], Optional[str]]:
    """Run the gate over every lawful-basis candidate on record for an asset.
    Allowed if ANY candidate passes. Returns (allowed, reasons, basis_used).
    With no candidates the reasons say no lawful basis is on record."""
    best_reasons: Optional[List[str]] = None
    for c in candidates:
        ok, reasons = check_listing(
            jurisdiction_cleared,
            do_no_harm_status,
            c.get("basis"),
            c.get("reference"),
            c.get("signing_events"),
            c.get("document_sha256"),
            bool(c.get("seller_holds_title", False)),
        )
        if ok:
            return True, [], c.get("basis")
        if best_reasons is None or len(reasons) < len(best_reasons):
            best_reasons = reasons
    if best_reasons is None:
        _, best_reasons = check_listing(jurisdiction_cleared, do_no_harm_status, None)
    return False, best_reasons, None
