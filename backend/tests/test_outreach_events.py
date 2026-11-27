import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.outreach_event import OutreachEvent  # noqa: F401
from app.services import outreach_events as oe


@pytest.fixture()
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng, tables=[OutreachEvent.__table__])
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def test_extracts_type_and_email_from_nested_payloads():
    p = {"eventType": "contact_opted_out", "data": {"contact": {"Email": "Jane@Example.com"}}}
    assert oe.extract_event_type(p) == "contact_opted_out" and oe.extract_email(p) == "jane@example.com"
    assert oe.extract_email({"items": [{"prospectEmail": "a@b.co"}]}) == "a@b.co"
    assert oe.extract_email({"email": "not-an-email"}) is None


def test_every_event_is_stored_raw_even_without_an_email(db):
    ev = oe.record_event(db, {"type": "email_bounced", "note": "no address here"})
    assert ev.event_type == "email_bounced" and ev.email is None and json.loads(ev.payload)["note"]
    assert oe.record_event(db, {"nothing": 1}).event_type == "unknown"


def test_only_opt_outs_suppress(db):
    oe.record_event(db, {"eventType": "email_bounced", "email": "bounce@x.com"})
    oe.record_event(db, {"eventType": "email_replied", "email": "reply@x.com"})
    oe.record_event(db, {"eventType": "contact_opted_out", "email": "Stop@X.com"})
    assert oe.is_suppressed(db, "stop@x.com") and oe.is_suppressed(db, " STOP@x.com ")
    assert not oe.is_suppressed(db, "bounce@x.com") and not oe.is_suppressed(db, "reply@x.com") and not oe.is_suppressed(db, "")


def test_bad_bodies_rejected(db):
    for bad in ("text", 5, None):
        with pytest.raises(oe.EventError):
            oe.record_event(db, bad)


def test_secret_compare_fails_closed():
    assert oe.secret_matches("s" * 40, "s" * 40)
    assert not oe.secret_matches("", "") and not oe.secret_matches("abc", "") and not oe.secret_matches("abc", "abd")
