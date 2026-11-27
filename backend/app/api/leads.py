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
from app.models.property_lead import LEAD_STATUSES, PropertyLead
from app.models.user import User
from app.services import lead_engine, outreach, outreach_events, public_sources
from app.services.outreach import OutreachCampaignType

router = APIRouter(prefix="/leads", tags=["leads"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def _to_dict(r: PropertyLead) -> dict:
    return {
        "id": r.id, "owner_name": r.owner_name, "address": r.address, "mailing_address": r.mailing_address,
        "city": r.city, "state": r.state, "zip": r.zip, "county": r.county, "parcel_id": r.parcel_id,
        "email": r.email, "phone": r.phone, "assessed_value": r.assessed_value, "mortgage_balance": r.mortgage_balance,
        "amount_owed": r.amount_owed, "property_type": r.property_type,
        "flags": [f for f in (r.flags or "").split(";") if f], "score": r.score, "status": r.status, "source": r.source,
        "dedupe_key": r.dedupe_key,
    }


_FIELDS = ("owner_name", "address", "mailing_address", "city", "state", "zip", "county", "parcel_id", "email",
           "phone", "assessed_value", "mortgage_balance", "amount_owed", "property_type")


def _upsert(db: Session, leads: List[dict], source: Optional[str]) -> dict:
    inserted = updated = 0
    keys = [l["dedupe_key"] for l in leads]
    existing: Dict[str, PropertyLead] = {}
    for i in range(0, len(keys), 500):
        for row in db.query(PropertyLead).filter(PropertyLead.dedupe_key.in_(keys[i:i + 500])).all():
            existing[row.dedupe_key] = row
    for lead in leads:
        row = existing.get(lead["dedupe_key"])
        if row is None:
            db.add(PropertyLead(**{k: lead.get(k) for k in _FIELDS}, dedupe_key=lead["dedupe_key"],
                                flags=";".join(lead["flags"]), score=lead["score"], status="new", source=source))
            inserted += 1
        else:
            merged = lead_engine.merge_leads(_to_dict(row), lead)
            for k in _FIELDS:
                setattr(row, k, merged.get(k))
            row.flags = ";".join(merged["flags"])
            row.score = merged["score"]
            updated += 1
    db.commit()
    return {"inserted": inserted, "updated": updated}


def _ingest(db: Session, rows: List[dict], mapping, source) -> dict:
    try:
        leads, rejected = lead_engine.normalize_batch(rows, mapping)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    out = _upsert(db, leads, source)
    out.update({"received": len(rows), "rejected": len(rejected), "rejected_detail": rejected[:50]})
    return out


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


def _filtered(db: Session, states, min_score, all_flags, any_flags, has_email, has_phone, county, status, limit):
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
    return rows[:limit]


@router.get("")
def list_leads(states: Optional[List[str]] = Query(None), min_score: int = 0,
               all_flags: Optional[List[str]] = Query(None), any_flags: Optional[List[str]] = Query(None),
               has_email: bool = False, has_phone: bool = False, county: Optional[str] = None,
               status: Optional[str] = None, limit: int = 100,
               db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """List stacking: all_flags = must have every one; any_flags = at least one. Best score first."""
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


@router.post("/push-outreach")
def push_to_outreach(body: PushIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Sends new leads that have an email to a real Reply.io campaign. Opted-out emails are skipped and
    marked do_not_contact. Each lead is marked contacted only after Reply.io accepted it."""
    rows = _filtered(db, body.states, body.min_score, body.all_flags, body.any_flags, True, False, body.county,
                     "new", min(max(body.limit, 1), 200))
    sent, skipped, failed = 0, 0, []
    for r in rows:
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
    return {"considered": len(rows), "sent": sent, "skipped_opted_out": skipped, "failed": failed}
