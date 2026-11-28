"""
Continuous lead search - runs 24/7 inside the platform, following the sun.

Every cycle it looks at each configured source (LEAD_SOURCES_JSON). A source is worked while its
own region is in daytime (its `timezone`), so as the sun moves around the world the worker is always
busy somewhere. Each pass pulls the next page of the portal, cleans/dedupes/scores it into the lead
table, and remembers its place (so a restart resumes). When a source runs out of rows it starts over
from the top on its next daytime pass, which picks up new and changed records.

One failing source never stops the others or the loop; the error is stored on the source's cursor
and shown at GET /leads/sources/status. Reports only what a source returned - nothing invented.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.property_lead import LeadSourceCursor
from app.services import follow_the_sun, lead_ingest, public_sources

log = logging.getLogger("pacific_rim.leads")


def load_sources(raw: str) -> List[dict]:
    """Parses LEAD_SOURCES_JSON. Bad entries are skipped (and logged), not fatal."""
    if not (raw or "").strip():
        return []
    try:
        items = json.loads(raw)
    except ValueError:
        log.error("LEAD_SOURCES_JSON is not valid JSON; lead worker has no sources")
        return []
    good, seen = [], set()
    for it in items if isinstance(items, list) else []:
        try:
            name = str(it["name"]).strip()
            public_sources.validate_portal(it["domain"], it["dataset_id"])
            tz = it.get("timezone")
            if tz:
                follow_the_sun.is_daytime(tz)   # raises if not a real time zone
            if not name or name in seen:
                raise ValueError("missing or repeated name")
        except Exception as exc:  # noqa: BLE001
            log.error("lead source skipped (%s): %s", exc, it)
            continue
        seen.add(name)
        good.append(it)
    return good


def source_is_active(src: dict, now_utc: Optional[datetime] = None) -> bool:
    tz = src.get("timezone")
    return True if not tz else follow_the_sun.is_daytime(tz, now_utc)


def run_source_once(db, src: dict) -> dict:
    """One page of one source. Updates the cursor. Never raises."""
    name = src["name"]
    cur = db.query(LeadSourceCursor).filter(LeadSourceCursor.name == name).first()
    if cur is None:
        cur = LeadSourceCursor(name=name, offset=0, pages_done=0)
        db.add(cur)
    page = max(1, min(int(src.get("page_size", 2000)), public_sources.MAX_ROWS))
    try:
        rows = public_sources.fetch_socrata(src["domain"], src["dataset_id"], limit=page, offset=cur.offset,
                                            where=src.get("where"), app_token=src.get("app_token"))
        if src.get("flags"):
            rows = [dict(r, **{"flags": ";".join(x for x in (str(r.get("flags") or ""), src["flags"]) if x)})
                    if isinstance(r, dict) else r for r in rows]
        result = lead_ingest.ingest_rows(db, rows, src.get("mapping"), f"{src['domain']}/{src['dataset_id']}")
        cur.offset = 0 if len(rows) < page else cur.offset + len(rows)
        cur.pages_done = (cur.pages_done or 0) + 1
        cur.last_error = None
        cur.last_result = json.dumps({k: result[k] for k in ("received", "inserted", "updated", "rejected")})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        cur = db.query(LeadSourceCursor).filter(LeadSourceCursor.name == name).first() or LeadSourceCursor(
            name=name, offset=0, pages_done=0)
        db.add(cur)
        cur.last_error = str(exc)[:500]
        log.warning("lead source %s failed: %s", name, exc)
    cur.last_run = datetime.utcnow()
    db.commit()
    return {"name": name, "last_result": cur.last_result, "last_error": cur.last_error}


def _cycle_sync() -> List[dict]:
    sources = load_sources(get_settings().lead_sources_json)
    out = []
    now = datetime.utcnow()
    for src in sources:
        if not source_is_active(src, now):
            continue
        with SessionLocal() as db:
            out.append(run_source_once(db, src))
    return out


async def lead_loop(stop: asyncio.Event) -> None:
    interval = max(60, get_settings().lead_loop_interval_seconds)
    while not stop.is_set():
        try:
            done = await asyncio.to_thread(_cycle_sync)
            if done:
                log.info("lead worker pass: %s", done)
        except Exception:  # noqa: BLE001
            log.exception("lead worker cycle failed; will retry")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
