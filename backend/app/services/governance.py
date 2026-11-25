"""
Freeze switch and expiring permission scope.

Two controls the architect holds:
  * FREEZE: while on, no new listing, publish or bid goes through. Reads,
    existing records and bank-confirmed revenue are untouched.
  * SCOPE (optional): limits what may happen and until when - by action,
    by a per-action amount cap, and by an expiry. Once a scope is set it is
    enforced and it fails closed: after expiry the guarded actions stop until
    a human sets a new scope or clears it. With no scope set, only the freeze
    applies. The platform never grants itself a scope.

Pure functions here; storage is models/governance.py, routes api/governance.py.
"""
from datetime import datetime
from typing import Optional, Tuple

ACTIONS = ("CREATE_LISTING", "PUBLISH_LISTING", "PLACE_BID")


def validate_scope(actions, limit_minor, expires_at: Optional[datetime], now: datetime) -> list:
    """Return a list of problems; empty means the scope may be saved."""
    problems = []
    if not expires_at:
        problems.append("expires_at is required: a scope without an expiry is not accepted.")
    elif expires_at <= now:
        problems.append("expires_at must be in the future.")
    if not actions:
        problems.append("actions is required: list one or more of " + ", ".join(ACTIONS) + ".")
    else:
        bad = [a for a in actions if a not in ACTIONS]
        if bad:
            problems.append("Unknown action(s): " + ", ".join(map(str, bad)))
    if limit_minor is not None and (not isinstance(limit_minor, int) or isinstance(limit_minor, bool) or limit_minor <= 0):
        problems.append("limit_minor must be a positive whole number of cents.")
    return problems


def evaluate(frozen: bool, scope: Optional[dict], action: str, amount_minor: Optional[int],
             now: datetime) -> Tuple[bool, Optional[str]]:
    """(allowed, reason). scope is None when no scope is set."""
    if frozen:
        return False, "FROZEN: the architect has frozen new activity."
    if scope is None:
        return True, None
    exp = scope.get("expires_at")
    if exp is None or now >= exp:
        return False, "SCOPE_EXPIRED: the permission scope has expired; a new one must be set."
    if action not in (scope.get("actions") or []):
        return False, f"OUT_OF_SCOPE: {action} is not covered by the current permission scope."
    limit = scope.get("limit_minor")
    if limit is not None and amount_minor is not None and amount_minor > limit:
        return False, "OVER_LIMIT: amount is above the permission scope's cap."
    return True, None
