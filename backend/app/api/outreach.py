from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.outreach import OutreachContactCreate
from app.services import outreach, outreach_events

router = APIRouter(prefix="/outreach", tags=["outreach"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/verify")
def verify_reply_io_connection(admin: User = Depends(require_admin)):
    """Confirms the Reply.io API key actually works, by actually calling
    Reply.io - not a hardcoded success message."""
    try:
        return outreach.verify_credentials()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io verification failed: {exc}")


@router.post("/contacts", status_code=201)
def add_outreach_contact(
    contact_in: OutreachContactCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add a contact for outreach (potential seller, agent/broker, or
    a buyer to follow up with) and enroll them in the specified real
    Reply.io campaign."""
    if outreach_events.is_suppressed(db, str(contact_in.email)):
        raise HTTPException(status_code=409, detail="This email has opted out of contact and cannot be added.")
    try:
        contact = outreach.add_contact(
            email=contact_in.email,
            first_name=contact_in.first_name,
            last_name=contact_in.last_name,
            company=contact_in.company,
            country=contact_in.country,
            custom_fields={"campaign_type": contact_in.campaign_type.value},
        )
        enrollment = outreach.add_contact_to_campaign(
            contact_id=contact["id"], campaign_id=contact_in.campaign_id
        )
        return {"contact": contact, "enrollment": enrollment}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")


@router.get("/campaigns/{campaign_id}/stats")
def get_campaign_stats(campaign_id: str, admin: User = Depends(require_admin)):
    """Real send/open/reply numbers for a campaign - straight from
    Reply.io, nothing estimated or projected."""
    try:
        return outreach.get_campaign_stats(campaign_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")


# ---------------- Reply.io / Jason AI webhooks ----------------
@router.post("/webhooks/reply/{secret}")
async def receive_reply_event(secret: str, request: Request, db: Session = Depends(get_db)):
    """Reply.io posts events here (replies, bounces, opt-outs, finished sequences). The secret in the
    address is the only protection Reply.io's webhooks offer, so it is compared in constant time and
    a wrong or missing secret looks like a page that does not exist."""
    configured = get_settings().reply_io_webhook_secret
    if not configured:
        raise HTTPException(status_code=503, detail="Webhook receiver is not configured (REPLY_IO_WEBHOOK_SECRET).")
    if not outreach_events.secret_matches(configured, secret):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        payload = await request.json()
        ev = outreach_events.record_event(db, payload)
    except (ValueError, outreach_events.EventError):
        raise HTTPException(status_code=400, detail="Event body must be a JSON object.")
    return {"received": True, "event_type": ev.event_type, "matched_email": ev.email is not None}


class WebhookSubscribeIn(BaseModel):
    base_url: str   # your public https address, e.g. https://pacificrimauctions.com


@router.post("/webhooks/subscribe")
def subscribe_reply_webhooks(body: WebhookSubscribeIn, admin: User = Depends(require_admin)):
    """Creates the Reply.io subscriptions (replies, bounces, opt-outs, finished sequences, autopilot
    stopped) pointing at this platform's receiver. Safe to call once; check /webhooks/events first."""
    st = get_settings()
    if not st.reply_io_webhook_secret:
        raise HTTPException(status_code=503, detail="Set REPLY_IO_WEBHOOK_SECRET first.")
    base = body.base_url.strip().rstrip("/")
    if not base.startswith("https://"):
        raise HTTPException(status_code=422, detail="base_url must be a public https address.")
    url = f"{base}{st.api_v1_prefix}/outreach/webhooks/reply/{st.reply_io_webhook_secret}"
    results = []
    for ev in outreach_events.SUBSCRIBE_EVENTS:
        try:
            results.append({"event": ev, "ok": True, "reply_io": outreach.create_webhook(ev, url)})
        except Exception as exc:
            results.append({"event": ev, "ok": False, "error": str(exc)})
    return {"results": results}


@router.get("/webhooks/events")
def reply_webhook_event_names(admin: User = Depends(require_admin)):
    try:
        return outreach.list_webhook_events()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")


@router.post("/webhooks/{webhook_id}/test")
def reply_webhook_test(webhook_id: str, admin: User = Depends(require_admin)):
    try:
        return outreach.test_webhook(webhook_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")


@router.get("/webhooks/{webhook_id}/logs")
def reply_webhook_logs(webhook_id: str, admin: User = Depends(require_admin)):
    try:
        return outreach.get_webhook_logs(webhook_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")


@router.get("/events")
def recent_outreach_events(limit: int = 50, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Most recent events Reply.io has pushed to this platform."""
    from app.models.outreach_event import OutreachEvent
    rows = db.query(OutreachEvent).order_by(OutreachEvent.received_at.desc()).limit(min(max(limit, 1), 200)).all()
    return [{"id": r.id, "event_type": r.event_type, "email": r.email, "received_at": r.received_at.isoformat()} for r in rows]
