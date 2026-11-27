"""
Legal review packets: the research-and-draft step that comes BEFORE
PATCH /jurisdiction-nodes/{id}/review.

  GET  /legal-review/template/{node_id}  an empty packet with the questions to research
  POST /legal-review/check               validate a packet; if ready, returns the exact
                                         body to submit to the review endpoint

Neither endpoint changes any record. Clearing a jurisdiction still happens
only through the review endpoint, by a named person.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.jurisdiction_nodes import require_admin_or_compliance
from app.core.database import get_db
from app.models.jurisdiction_node import JurisdictionNode
from app.models.user import User
from app.core.config import get_settings
from app.services import astra_draft, audit, legal_review

router = APIRouter(prefix="/legal-review", tags=["legal-review"])


class PacketIn(BaseModel):
    packet: dict


@router.get("/template/{node_id}")
def template(node_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_compliance)):
    node = db.query(JurisdictionNode).filter(JurisdictionNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Jurisdiction node not found")
    return legal_review.build_template(node.country_code, node.country_name, node.region_code)


@router.post("/check")
def check(body: PacketIn, _: User = Depends(require_admin_or_compliance)):
    ready, problems = legal_review.validate_packet(body.packet)
    out = {"ready": ready, "problems": problems}
    if ready:
        out["review_payload"] = legal_review.to_review_payload(body.packet)
    return out


@router.post("/draft/{node_id}")
def draft_with_astra(node_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin_or_compliance)):
    """Ask Astra to DRAFT the research packet for one jurisdiction. Changes no jurisdiction record.
    The draft cannot pass /check until a named person verifies the sources and signs it."""
    node = db.query(JurisdictionNode).filter(JurisdictionNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Jurisdiction node not found")
    st = get_settings()
    if not astra_draft.is_configured(st.openai_api_key, st.astra_model):
        raise HTTPException(status_code=503, detail="Astra is not configured (OPENAI_API_KEY and ASTRA_MODEL are required).")
    try:
        out = astra_draft.draft_packet(
            node.country_code, node.country_name, node.region_code,
            api_key=st.openai_api_key, model=st.astra_model, base_url=st.openai_base_url, timeout=st.astra_timeout_seconds,
        )
    except astra_draft.AstraError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    audit.record_audit_event(db, user.id, "jurisdiction_node", node.id, "astra_draft_created",
                             actor_role=str(getattr(user.role, "value", user.role)), notes=f"model={out['model']}")
    db.commit()
    return out
