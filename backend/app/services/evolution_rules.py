"""
Autonomous Algorithm Evolution: the RULES (pure, standard library only).

The system may tune only parameters listed in PARAMETERS, only inside their
hard bounds, and only with evidence that security, legal compliance and
financial integrity are unaffected. Everything in PROTECTED can never be
changed by the evolution engine, however it is asked.
"""
from typing import Dict, Optional, Tuple

# name -> (minimum, maximum). Values are integers.
PARAMETERS: Dict[str, Tuple[int, int]] = {
    "min_bid_increment_minor": (1, 1_000_000),       # 1 cent to $10,000.00
    "anti_snipe_window_seconds": (10, 120),
    "anti_snipe_extension_seconds": (10, 120),
}

# Never autonomously changeable (spec section 8: the authority hierarchy).
PROTECTED = frozenset({
    "do_no_harm_policy", "law_of_the_land_policy", "compliance_engine",
    "security_foundations", "cryptographic_integrity", "signing_keys",
    "audit_history", "financial_accounting_controls", "immutable_memory_history",
    "authority_hierarchy", "platform_fee_min", "platform_fee_max",
    "settlement_destination", "memory_signing_secret",
})

REQUIRED_EVIDENCE_FLAGS = ("security_ok", "compliance_ok", "financial_integrity_ok")


def validate_change(name: str, new_value, evidence: Optional[dict]) -> Tuple[bool, str]:
    """Returns (allowed, reason). First failing rule wins."""
    if name in PROTECTED:
        return False, "PROTECTED_PARAMETER: this can never be changed autonomously."
    if name not in PARAMETERS:
        return False, "UNKNOWN_PARAMETER: only approved algorithmic parameters can be tuned."
    if isinstance(new_value, bool) or not isinstance(new_value, int):
        return False, "INVALID_VALUE: parameter values are whole numbers."
    low, high = PARAMETERS[name]
    if not (low <= new_value <= high):
        return False, f"OUT_OF_BOUNDS: must be between {low} and {high}."
    evidence = evidence or {}
    for flag in REQUIRED_EVIDENCE_FLAGS:
        if evidence.get(flag) is not True:
            return False, f"EVIDENCE_MISSING: {flag} must be true; uncertain changes are not executed."
    if not evidence.get("measurements"):
        return False, "EVIDENCE_MISSING: performance measurements are required."
    return True, "OK"


def should_auto_revert(metrics: dict, thresholds: dict) -> Optional[str]:
    """Predefined safety thresholds. Returns the violated metric name, or None.
    A missing metric counts as a violation, because uncertainty is never
    treated as safe."""
    for metric, limit in thresholds.items():
        value = metrics.get(metric)
        if value is None:
            return f"{metric} (not reported)"
        if value > limit:
            return metric
    return None
