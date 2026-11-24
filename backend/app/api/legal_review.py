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
from app.services import legal_review

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
