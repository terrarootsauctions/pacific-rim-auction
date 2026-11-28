"""Shared lead saving: used by the leads API and by the continuous follow-the-sun lead worker."""
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models.property_lead import PropertyLead
from app.services import lead_engine


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


def ingest_rows(db: Session, rows: List[dict], mapping, source) -> dict:
    """Clean, de-duplicate, flag, score and save a batch. Raises ValueError for an oversize batch."""
    leads, rejected = lead_engine.normalize_batch(rows, mapping)
    out = _upsert(db, leads, source)
    reasons: Dict[str, int] = {}
    for r in rejected:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    out.update({"received": len(rows), "distinct_properties": len(leads), "rejected": len(rejected),
                "rejected_reasons": reasons, "rejected_detail": rejected[:50]})
    return out


