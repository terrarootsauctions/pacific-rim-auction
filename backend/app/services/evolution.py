"""
Autonomous Algorithm Evolution Engine - database layer.

The rules live in evolution_rules.py (pure and unit-tested). This layer
reads the live parameters the auction engine uses, applies validated
changes, and records EVERY outcome in the Memory Lock, including refusals,
failures and rollbacks. Nothing here can erase history: parameters keep
their previous value, and every change is a new immutable ALGORITHM_CHANGE
record answering: what changed, why, when, previous version, new version,
what evidence supported it, and was it reversed.

HONEST LIMIT: this engine APPLIES, VALIDATES, RECORDS and REVERTS bounded
changes. It does not invent proposals on its own, because a trustworthy
proposal needs real production telemetry, which only exists after the
platform has run. Proposals come from the SI / architect through the admin
API, and the same engine handles them with the same safety rules.
"""
import uuid
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.algorithm import AlgorithmParameter
from app.services import evolution_rules as rules
from app.services import memory_lock

settings = get_settings()

DEFAULTS = {
    "min_bid_increment_minor": lambda: settings.min_bid_increment_minor,
    "anti_snipe_window_seconds": lambda: settings.anti_snipe_window_seconds,
    "anti_snipe_extension_seconds": lambda: settings.anti_snipe_extension_seconds,
}


def get_params(db: Session) -> Dict[str, int]:
    """Live parameter values: configured defaults, overridden by any applied change."""
    values = {name: fn() for name, fn in DEFAULTS.items()}
    for row in db.query(AlgorithmParameter).all():
        if row.name in values:
            values[row.name] = int(row.value)
    return values


def _record(db, actor_id, payload):
    return memory_lock.capture(
        db, memory_lock.EventType.ALGORITHM_CHANGE, payload, actor_id=actor_id
    )


def propose_change(
    db: Session,
    name: str,
    new_value,
    reason: str,
    evidence: Optional[dict],
    actor_id: Optional[str],
) -> Dict:
    improvement_id = str(uuid.uuid4())
    current = get_params(db).get(name)
    allowed, why = rules.validate_change(name, new_value, evidence)

    base = {
        "improvement_id": improvement_id,
        "parameter": name,
        "previous_value": current,
        "proposed_value": new_value if isinstance(new_value, (int, str)) else str(new_value),
        "reason": reason,
        "evidence": evidence or {},
    }
    if not allowed:
        _record(db, actor_id, {**base, "result": "REJECTED", "result_detail": why,
                               "rollback_status": "NOT_APPLICABLE"})
        db.commit()
        return {"improvement_id": improvement_id, "result": "REJECTED", "detail": why}

    if current == new_value:
        return {"improvement_id": improvement_id, "result": "NO_CHANGE",
                "detail": "Parameter already has this value."}

    row = db.get(AlgorithmParameter, name)
    if row is None:
        row = AlgorithmParameter(name=name, value=new_value, previous_value=current,
                                 version=2, updated_by=actor_id)
        db.add(row)
        old_version = 1
    else:
        old_version = row.version
        row.previous_value = row.value
        row.value = new_value
        row.version = old_version + 1
        row.updated_by = actor_id

    _record(db, actor_id, {**base, "previous_version": old_version, "new_version": old_version + 1,
                           "result": "DEPLOYED", "rollback_status": "NOT_ROLLED_BACK"})
    db.commit()
    return {"improvement_id": improvement_id, "result": "DEPLOYED",
            "parameter": name, "previous_value": current, "new_value": new_value}


def rollback(db: Session, name: str, reason: str, actor_id: Optional[str]) -> Dict:
    """Restore the previous value. The rollback itself is a new immutable
    record; the original change record is never altered."""
    row = db.get(AlgorithmParameter, name)
    if row is None or row.previous_value is None:
        return {"result": "NOTHING_TO_ROLL_BACK"}
    restored, replaced = int(row.previous_value), int(row.value)
    old_version = row.version
    row.value = restored
    row.previous_value = replaced
    row.version = old_version + 1
    row.updated_by = actor_id
    _record(db, actor_id, {
        "improvement_id": str(uuid.uuid4()), "parameter": name,
        "previous_value": replaced, "new_value": restored,
        "previous_version": old_version, "new_version": old_version + 1,
        "reason": reason, "result": "ROLLED_BACK", "rollback_status": "ROLLED_BACK",
    })
    db.commit()
    return {"result": "ROLLED_BACK", "parameter": name, "restored_value": restored}


def evaluate_and_revert(db: Session, name: str, metrics: dict, thresholds: dict,
                        actor_id: Optional[str]) -> Dict:
    """Automatic revert when predefined safety thresholds are violated.
    Missing metrics count as a violation."""
    violated = rules.should_auto_revert(metrics, thresholds)
    if violated is None:
        return {"result": "WITHIN_THRESHOLDS"}
    out = rollback(db, name, f"Automatic revert: safety threshold violated ({violated})", actor_id)
    out["violated"] = violated
    return out
