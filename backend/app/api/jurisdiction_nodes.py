from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.jurisdiction_node import JurisdictionNode, NodeStatus
from app.models.user import User
from app.schemas.jurisdiction_node import CheckFailureResolution, JurisdictionNodeOut, JurisdictionNodeReview
from app.services.audit import record_audit_event
from app.services.precedent import build_match_key, save_precedent
from app.services.si_orchestrator import jurisdiction_node_coverage

router = APIRouter(prefix="/jurisdiction-nodes", tags=["jurisdiction-nodes"])


def require_admin_or_compliance(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.COMPLIANCE_OFFICER):
        raise HTTPException(status_code=403, detail="Admin or compliance officer access required")
    return current_user


@router.get("/", response_model=List[JurisdictionNodeOut])
def list_nodes(
    country_code: Optional[str] = None,
    status: Optional[NodeStatus] = None,
    db: Session = Depends(get_db),
):
    query = db.query(JurisdictionNode)
    if country_code:
        query = query.filter(JurisdictionNode.country_code == country_code.upper())
    if status:
        query = query.filter(JurisdictionNode.status == status)
    return query.limit(500).all()


@router.get("/coverage")
def get_coverage(db: Session = Depends(get_db)):
    """Honest summary: how many of the (up to 2,500) nodes are
    structurally present versus actually reviewed and active."""
    return jurisdiction_node_coverage(db)


@router.get("/{node_id}", response_model=JurisdictionNodeOut)
def get_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(JurisdictionNode).filter(JurisdictionNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Jurisdiction node not found")
    return node


@router.patch("/{node_id}/review", response_model=JurisdictionNodeOut)
def review_node(
    node_id: str,
    review: JurisdictionNodeReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_compliance),
):
    """The ONLY way a node moves out of PENDING_REVIEW. Requires a named
    human reviewer - never set automatically, never set in bulk."""
    node = db.query(JurisdictionNode).filter(JurisdictionNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Jurisdiction node not found")

    before = f"status={node.status.value}, disclosure={node.disclosure_requirements}"

    node.status = review.status
    node.disclosure_requirements = review.disclosure_requirements
    node.licensing_requirements = review.licensing_requirements
    node.sanctions_notes = review.sanctions_notes
    node.reviewed_by = review.reviewed_by
    node.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(node)

    after = f"status={node.status.value}, disclosure={node.disclosure_requirements}"
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="jurisdiction_node",
        entity_id=node.id,
        action="reviewed",
        before_state=before,
        after_state=after,
        notes=f"reviewed_by field: {review.reviewed_by}",
    )

    return node


@router.patch("/{node_id}/resolve-failure", response_model=JurisdictionNodeOut)
def resolve_check_failure(
    node_id: str,
    resolution: CheckFailureResolution,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_compliance),
):
    """Resolves a node currently in CHECK_FAILED status. By default, also
    saves this resolution as a precedent (per the architect's directive):
    if the exact same failure (same country/region/reason/source) happens
    again in the future, it will be auto-resolved the same way instead of
    being flagged again. Set save_as_precedent=False to resolve just this
    one case without creating a standing rule."""
    node = db.query(JurisdictionNode).filter(JurisdictionNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Jurisdiction node not found")
    if node.status != NodeStatus.CHECK_FAILED:
        raise HTTPException(status_code=400, detail=f"Node is not in CHECK_FAILED status (currently: {node.status.value})")

    before = f"status={node.status.value}, reason={node.last_check_failure_reason}"
    reason_code = node.last_check_failure_reason or "unknown"
    source = node.last_check_source or "unknown"

    node.status = resolution.new_status
    db.commit()
    db.refresh(node)

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        entity_type="jurisdiction_node",
        entity_id=node.id,
        action="check_failure_resolved",
        before_state=before,
        after_state=f"status={node.status.value}",
        notes=resolution.resolution_notes,
    )

    if resolution.save_as_precedent:
        match_key = build_match_key(
            country=node.country_code,
            region=node.region_code or "national",
            reason=reason_code,
            source=source,
        )
        save_precedent(
            db,
            entity_type="jurisdiction_node",
            issue_type="check_failed",
            match_key=match_key,
            resolution_status=resolution.new_status.value,
            resolved_by_user_id=current_user.id,
            resolution_notes=resolution.resolution_notes,
        )

    return node
