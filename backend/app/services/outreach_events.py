"""
Reply.io / Jason AI event handling. Pure rules plus small database helpers; no network.

  * Every event is stored exactly as received.
  * An opt-out (contact_opted_out) puts that email on a do-not-contact list; add_outreach_contact
    refuses suppressed emails. Bounces are recorded but do not suppress (a temporary bounce is
    not a refusal).
  * Reply.io's docs do not publish the payload layout, so the email is found by searching the
    payload for a known email field. If none is found the event is still stored, and the log
    says so. An opt-out without an email cannot be matched to a contact.
"""
import hmac
import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.outreach_event import OutreachEvent

SUPPRESSING_EVENTS = {"contact_opted_out"}
SUBSCRIBE_EVENTS = ["email_replied", "reply_categorized", "email_bounced", "contact_opted_out",
                    "contact_replied", "contact_finished", "autopilot_stopped"]
_TYPE_KEYS = ("eventtype", "event_type", "type", "event")
_EMAIL_KEYS = ("email", "contactemail", "prospectemail", "recipientemail", "toemail")


class EventError(ValueError):
    pass


def secret_matches(configured: str, given: str) -> bool:
    return bool(configured) and bool(given) and hmac.compare_digest(configured.encode(), given.encode())


def _find(obj: Any, keys, want_email: bool = False) -> Optional[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in keys and isinstance(v, str) and v.strip() and (not want_email or "@" in v):
                return v.strip()
        for v in obj.values():
            r = _find(v, keys, want_email)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, keys, want_email)
            if r:
                return r
    return None


def extract_event_type(payload: Any) -> Optional[str]:
    return _find(payload, _TYPE_KEYS)


def extract_email(payload: Any) -> Optional[str]:
    e = _find(payload, _EMAIL_KEYS, want_email=True)
    return e.lower() if e else None


def record_event(db: Session, payload: Any) -> OutreachEvent:
    if not isinstance(payload, (dict, list)):
        raise EventError("Event body must be a JSON object.")
    etype = extract_event_type(payload) or "unknown"
    ev = OutreachEvent(event_type=etype[:100], email=extract_email(payload), payload=json.dumps(payload)[:100000])
    db.add(ev)
    db.commit()
    return ev


def is_suppressed(db: Session, email: str) -> bool:
    if not email:
        return False
    return db.query(OutreachEvent.id).filter(OutreachEvent.email == email.strip().lower(),
                                             OutreachEvent.event_type.in_(SUPPRESSING_EVENTS)).first() is not None
