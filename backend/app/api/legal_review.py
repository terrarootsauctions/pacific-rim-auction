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
from app.services import astra_docs, astra_draft, audit, doc_completeness, legal_review

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
            effort=st.astra_reasoning_effort, web_search=st.astra_web_search,
        )
    except astra_draft.AstraError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    audit.record_audit_event(db, user.id, "jurisdiction_node", node.id, "astra_draft_created",
                             actor_role=str(getattr(user.role, "value", user.role)), notes=f"model={out['model']}")
    db.commit()
    return out


class DocCheckIn(BaseModel):
    document_text: str
    statements: list
    confirm_send_to_provider: bool = False
    reference: str = ""   # what this is about, e.g. a listing or claim id (stored in the audit log; no document text is)


@router.post("/document-check")
def document_check(body: DocCheckIn, db: Session = Depends(get_db), user: User = Depends(require_admin_or_compliance)):
    """Ask Astra whether a document supports given statements. Advisory only: records nothing except an audit entry."""
    st = get_settings()
    if not astra_draft.is_configured(st.openai_api_key, st.astra_model):
        raise HTTPException(status_code=503, detail="Astra is not configured (OPENAI_API_KEY and ASTRA_MODEL are required).")
    try:
        out = astra_docs.check_document(
            body.document_text, body.statements, body.confirm_send_to_provider,
            api_key=st.openai_api_key, model=st.astra_model, base_url=st.openai_base_url, timeout=st.astra_timeout_seconds,
            effort=st.astra_reasoning_effort,
        )
    except astra_docs.RequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except astra_draft.AstraError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    audit.record_audit_event(db, user.id, "document_check", (body.reference or "unspecified")[:100], "astra_document_check",
                             actor_role=str(getattr(user.role, "value", user.role)),
                             notes=f"model={out['model']} statements={len(body.statements)}")
    db.commit()
    return out


class CompletenessIn(BaseModel):
    doc_type: str
    document_text: str
    reference: str = ""


@router.post("/document-completeness")
def document_completeness(body: CompletenessIn, db: Session = Depends(get_db), user: User = Depends(require_admin_or_compliance)):
    """Our own rules, no outside service: which expected elements appear in a document, with the exact words.
    Presence check only; records nothing except an audit entry (no document text in it)."""
    try:
        out = doc_completeness.check_completeness(body.doc_type, body.document_text)
    except doc_completeness.DocError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit.record_audit_event(db, user.id, "document_check", (body.reference or "unspecified")[:100], "document_completeness_check",
                             actor_role=str(getattr(user.role, "value", user.role)),
                             notes=f"type={body.doc_type} missing={len(out['missing'])}")
    db.commit()
    return out
