"""
OneTrust compliance checkpoint (hard-coded gate at publish time).

OneTrust is an external service. This module is the permanent connection
point for it, and it is deliberately honest:

  * ONETRUST_ENFORCE=false (default): the checkpoint runs, reports
    "not enforced" in the record, and does not block. Jurisdiction review
    and the compliance gate still apply.
  * ONETRUST_ENFORCE=true: going live is REFUSED unless OneTrust is both
    configured and able to clear the listing. Because OneTrust's API contract
    for your tenant has not been supplied, a configured-but-unimplemented
    call fails CLOSED (refuses) rather than pretending to clear anything.

When you have your OneTrust API documentation, implement `_query_onetrust`
below; nothing else needs to change.
"""
from typing import Tuple

from app.core.config import get_settings

settings = get_settings()


def status() -> dict:
    configured = bool(settings.onetrust_api_base_url and settings.onetrust_api_token)
    return {
        "configured": configured,
        "enforced": settings.onetrust_enforce,
        "state": (
            "connected_and_enforced" if configured and settings.onetrust_enforce
            else "configured_not_enforced" if configured
            else "not_connected"
        ),
        "api_contract_implemented": False,
    }


def _query_onetrust(listing) -> Tuple[bool, str]:
    """Replace with the real OneTrust call once its API specification for
    your tenant is available. Until then it cannot clear anything."""
    return False, "OneTrust API integration is pending the provider's API specification."


def check_listing(listing) -> Tuple[bool, str]:
    st = status()
    if not st["enforced"]:
        return True, f"OneTrust checkpoint not enforced (state: {st['state']})."
    if not st["configured"]:
        return False, "OneTrust is required but not connected; refusing to go live (no guessing)."
    return _query_onetrust(listing)
