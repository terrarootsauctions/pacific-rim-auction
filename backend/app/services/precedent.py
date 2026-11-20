"""
Precedent service - implements the architect's directive: if SI has
already faced this EXACT issue before and a human resolved it, apply that
same resolution automatically rather than asking again. Anything that
isn't an exact match is new and still goes to a human.

This is NOT an attempt to model the architect's reasoning or "think like"
anyone. It is a literal lookup: has this precise situation, defined by an
exact match_key, been decided before? If yes, repeat that decision and
log that it was repeated. If no, there is nothing to apply - flag it for
a human, the same as today.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.precedent_log import PrecedentLog
from app.services.audit import record_audit_event


def build_match_key(**dimensions: str) -> str:
    """Builds a strict, literal match key from named dimensions, e.g.
    build_match_key(country='ID', category='natural_resource', reason='no_disclosure_rule_found')
    -> 'category=natural_resource|country=ID|reason=no_disclosure_rule_found'

    Sorted by dimension name so the same inputs always produce the same
    key regardless of argument order. No fuzzing, no partial matching -
    this is exact-string lookup only."""
    parts = [f"{k}={v}" for k, v in sorted(dimensions.items())]
    return "|".join(parts)


def find_precedent(db: Session, entity_type: str, issue_type: str, match_key: str) -> Optional[PrecedentLog]:
    """Exact-match lookup only. A near-miss on any dimension returns
    None, which means: treat this as new, flag it for a human."""
    return (
        db.query(PrecedentLog)
        .filter(
            PrecedentLog.entity_type == entity_type,
            PrecedentLog.issue_type == issue_type,
            PrecedentLog.match_key == match_key,
        )
        .first()
    )


def apply_precedent(db: Session, precedent: PrecedentLog, entity_id: str) -> PrecedentLog:
    """Records that a saved human decision was reused for a new but
    identical case. This is always logged - reuse is never silent."""
    precedent.times_applied = (precedent.times_applied or 0) + 1
    db.commit()
    db.refresh(precedent)

    record_audit_event(
        db,
        actor_user_id=precedent.resolved_by_user_id,
        entity_type=precedent.entity_type,
        entity_id=entity_id,
        action="precedent_applied",
        before_state=f"matched precedent {precedent.id} (key={precedent.match_key})",
        after_state=f"resolution_status={precedent.resolution_status}",
        notes=f"Originally decided by user {precedent.resolved_by_user_id} on "
        f"{precedent.resolved_at.isoformat() if precedent.resolved_at else 'unknown date'}. "
        f"Applied automatically because this case exactly matches that prior decision. "
        f"Applied {precedent.times_applied} time(s) total.",
    )
    return precedent


def save_precedent(
    db: Session,
    entity_type: str,
    issue_type: str,
    match_key: str,
    resolution_status: str,
    resolved_by_user_id: str,
    resolution_notes: Optional[str] = None,
) -> PrecedentLog:
    """Saves a NEW human decision as a precedent. Only ever called when a
    human actually makes a real decision - never auto-generated."""
    precedent = PrecedentLog(
        entity_type=entity_type,
        issue_type=issue_type,
        match_key=match_key,
        resolution_status=resolution_status,
        resolution_notes=resolution_notes,
        resolved_by_user_id=resolved_by_user_id,
        times_applied=0,
    )
    db.add(precedent)
    db.commit()
    db.refresh(precedent)
    return precedent
