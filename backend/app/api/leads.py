"""
Property lead pipeline (admin only). Import records from a CSV, JSON, or a free public open-data
portal; they are cleaned, de-duplicated, flagged and scored; list-stack and export them; send the
contactable ones to Reply.io outreach (opted-out emails are never sent). See LEADS.md.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.property_lead import LEAD_STATUSES, LeadSourceCursor, PropertyLead
from app.models.user import User
from app.services import lead_engine, outreach, outreach_events, public_sources
from app.services.lead_ingest import _to_dict, ingest_rows
from app.services.outreach import OutreachCampaignType

router = APIRouter(prefix="/leads", tags=["leads"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def _ingest(db: Session, rows: List[dict], mapping, source) -> dict:
    try:
        return ingest_rows(db, rows, mapping, source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class ImportRecords(BaseModel):
    records: List[dict]
    mapping: Optional[Dict[str, str]] = None   # {canonical_field: your_column_name}
    source: Optional[str] = None


class ImportCsv(BaseModel):
    csv_text: str
    mapping: Optional[Dict[str, str]] = None
    source: Optional[str] = None


class ImportOpenData(BaseModel):
    domain: str                      # e.g. data.somecounty.gov
    dataset_id: str                  # e.g. abcd-1234
    mapping: Optional[Dict[str, str]] = None
    where: Optional[str] = None      # SoQL filter, e.g. "amount_due > 1000"
    limit: int = 1000
    offset: int = 0
    app_token: Optional[str] = None


@router.post("/import")
def import_records(body: ImportRecords, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return _ingest(db, body.records, body.mapping, body.source)


@router.post("/import-csv")
def import_csv(body: ImportCsv, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        rows = lead_engine.parse_csv(body.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _ingest(db, rows, body.mapping, body.source)


@router.post("/import-open-data")
def import_open_data(body: ImportOpenData, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        rows = public_sources.fetch_socrata(body.domain, body.dataset_id, limit=body.limit, offset=body.offset,
                                            where=body.where, app_token=body.app_token)
    except public_sources.SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _ingest(db, rows, body.mapping, f"{body.domain}/{body.dataset_id}")


def _filtered(db: Session, states, min_score, all_flags, any_flags, has_email, has_phone, county, status, limit, sort="revenue",
              include_expired=False):
    q = db.query(PropertyLead)
    if states:
        q = q.filter(PropertyLead.state.in_([s.upper() for s in states]))
    if min_score:
        q = q.filter(PropertyLead.score >= min_score)
    if status:
        q = q.filter(PropertyLead.status == status)
    if has_email:
        q = q.filter(PropertyLead.email.isnot(None))
    if has_phone:
        q = q.filter(PropertyLead.phone.isnot(None))
    if county:
        q = q.filter(PropertyLead.county.ilike(county))
    rows = [_to_dict(r) for r in q.order_by(PropertyLead.score.desc()).limit(50000).all()]
    rows = [r for r in rows if lead_engine.matches(r, all_flags=all_flags, any_flags=any_flags)]
    if not include_expired:
        rows = [r for r in rows if "claims_expired" not in r["flags"]]   # closed-claim leads are never shown or worked
    if sort == "revenue":
        rows.sort(key=lambda r: (r["est_revenue"], r["score"]), reverse=True)
    return rows[:limit]


@router.get("")
def list_leads(states: Optional[List[str]] = Query(None), min_score: int = 0,
               all_flags: Optional[List[str]] = Query(None), any_flags: Optional[List[str]] = Query(None),
               has_email: bool = False, has_phone: bool = False, county: Optional[str] = None,
               status: Optional[str] = None, limit: int = 100,
               db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """List stacking: all_flags = must have every one; any_flags = at least one. Highest estimated revenue first (est_revenue = Stage A: unclaimed amount held, 100%; Stage B: 5% of assessed value; estimates from the record, not forecasts)."""
    rows = _filtered(db, states, min_score, all_flags, any_flags, has_email, has_phone, county, status,
                     min(max(limit, 1), 1000))
    return {"count": len(rows), "leads": rows}


@router.get("/export.csv", response_class=PlainTextResponse)
def export_leads(states: Optional[List[str]] = Query(None), min_score: int = 0,
                 all_flags: Optional[List[str]] = Query(None), any_flags: Optional[List[str]] = Query(None),
                 has_email: bool = False, has_phone: bool = False, county: Optional[str] = None,
                 status: Optional[str] = None, limit: int = 10000,
                 db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = _filtered(db, states, min_score, all_flags, any_flags, has_email, has_phone, county, status,
                     min(max(limit, 1), 50000))
    return PlainTextResponse(lead_engine.to_csv(rows), media_type="text/csv")


class StatusIn(BaseModel):
    status: str


@router.patch("/{lead_id}/status")
def set_status(lead_id: str, body: StatusIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if body.status not in LEAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(LEAD_STATUSES)}")
    row = db.query(PropertyLead).filter(PropertyLead.id == lead_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    row.status = body.status
    db.commit()
    return _to_dict(row)


class PushIn(BaseModel):
    campaign_id: str
    campaign_type: OutreachCampaignType = OutreachCampaignType.ASSET_SOURCING
    states: Optional[List[str]] = None
    min_score: int = 0
    all_flags: Optional[List[str]] = None
    any_flags: Optional[List[str]] = None
    county: Optional[str] = None
    limit: int = 100   # max 200 per call
    include_claims_expired: bool = False   # True = also contact leads whose source says the claim deadline passed


@router.post("/push-outreach")
def push_to_outreach(body: PushIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Sends new leads that have an email to a real Reply.io campaign. Opted-out emails are skipped and
    marked do_not_contact. Each lead is marked contacted only after Reply.io accepted it."""
    rows = _filtered(db, body.states, body.min_score, body.all_flags, body.any_flags, True, False, body.county,
                     "new", min(max(body.limit, 1), 200), include_expired=body.include_claims_expired)
    sent, skipped, failed, held = 0, 0, [], 0
    for r in rows:
        if "claims_expired" in r["flags"] and not body.include_claims_expired:
            held += 1   # the source says claims are closed; not told they can claim until the source reopens them
            continue
        row = db.query(PropertyLead).filter(PropertyLead.id == r["id"]).first()
        if outreach_events.is_suppressed(db, r["email"]):
            row.status = "do_not_contact"
            db.commit()
            skipped += 1
            continue
        first, last, company = lead_engine.split_owner_name(r["owner_name"])
        try:
            contact = outreach.add_contact(
                email=r["email"], first_name=first, last_name=last, company=company, country="US",
                custom_fields={"campaign_type": body.campaign_type.value, "property_address": r["address"],
                               "lead_flags": ";".join(r["flags"])})
            outreach.add_contact_to_campaign(contact_id=contact["id"], campaign_id=body.campaign_id)
        except Exception as exc:
            failed.append({"id": r["id"], "error": str(exc)})
            if len(failed) >= 5:
                break   # Reply.io is failing; stop instead of hammering it
            continue
        row.status = "contacted"
        db.commit()
        sent += 1
    return {"considered": len(rows), "sent": sent, "skipped_opted_out": skipped, "held_claims_expired": held, "failed": failed}


@router.get("/sources/status")
def lead_sources_status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """What the 24/7 worker is doing: each configured source, whether its region is in daytime now,
    where it is in the portal, and its last result or error."""
    from app.core.config import get_settings
    from app.services import lead_worker
    srcs = lead_worker.load_sources(get_settings().lead_sources_json)
    cursors = {c.name: c for c in db.query(LeadSourceCursor).all()}
    out = []
    for s in srcs:
        c = cursors.get(s["name"])
        out.append({"name": s["name"], "portal": f"{s['domain']}/{s.get('dataset_id') or s.get('resource_id')}", "timezone": s.get("timezone"),
                    "working_now": lead_worker.source_is_active(s), "offset": c.offset if c else 0,
                    "passes": c.pages_done if c else 0, "last_run": c.last_run.isoformat() if c and c.last_run else None,
                    "last_result": c.last_result if c else None, "last_error": c.last_error if c else None})
    total = db.query(PropertyLead).count()
    hidden = db.query(PropertyLead).filter(PropertyLead.flags.like("%claims_expired%")).count()
    return {"worker_enabled": get_settings().lead_loop_enabled, "sources": out, "total_leads": total, "hidden_claims_closed": hidden}
