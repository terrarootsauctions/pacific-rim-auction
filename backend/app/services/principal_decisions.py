"""Applies the Principal's RECORDED country-clearance decisions.

Only decisions the Principal made in his own words are listed here, each
with the verbatim text and date (see docs/governance/decisions/). Nothing
else is cleared by this module. On startup, each listed node that is still
PENDING_REVIEW is set ACTIVE with the Principal named as reviewer, and an
audit record is written. A node a human has since set to RESTRICTED,
SUSPENDED or CHECK_FAILED is never overridden. If anything is missing
(node, admin user) nothing is applied: fail closed.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.jurisdiction_node import JurisdictionNode, NodeStatus
from app.models.user import User
from app.services.audit import record_audit_event
from app.services.principal_decision_data import DECISIONS, PRINCIPAL, should_apply

def apply_recorded_decisions(db: Session) -> List[str]:
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    results: List[str] = []
    for d in DECISIONS:
        label = f"{d['country_code']}/{d['region_code']}"
        node: Optional[JurisdictionNode] = (
            db.query(JurisdictionNode)
            .filter(JurisdictionNode.country_code == d["country_code"],
                    JurisdictionNode.region_code == d["region_code"])
            .first()
        )
        if node is None:
            results.append(f"{label}: node not found - nothing applied")
            continue
        if not should_apply(node.status.value):
            results.append(f"{label}: already {node.status.value} - left as is")
            continue
        if admin is None:
            results.append(f"{label}: no admin user to attribute the audit record - nothing applied")
            continue
        before = f"status={node.status.value}"
        node.status = NodeStatus.ACTIVE
        node.reviewed_by = PRINCIPAL
        node.reviewed_at = datetime.utcnow()
        record_audit_event(
            db, admin.id, "jurisdiction_node", node.id, "principal_decision_applied",
            before_state=before, after_state="status=active",
            actor_role=admin.role.value if hasattr(admin.role, "value") else str(admin.role),
            notes=f'Principal Decision, {d["decided_on"]}: "{d["text"]}" (record: {d["record"]})',
        )
        results.append(f"{label}: set ACTIVE per Principal Decision")
    db.commit()
    return results
