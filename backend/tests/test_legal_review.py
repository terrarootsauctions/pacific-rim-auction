from datetime import date

import pytest

from app.services import legal_review as lr

TODAY = date(2026, 11, 23)
TEXT = "Sellers must give the buyer a written disclosure of known defects before closing, per the cited statute."
CITE = {"source": "Example Gazette", "reference": "Property Act s.12(3)", "retrieved_on": "2026-11-20"}


def good(status="active"):
    p = lr.build_template("XX", "Exampleland")
    for s in lr.SECTIONS:
        p["sections"][s]["text"] = TEXT
        p["sections"][s]["citations"] = [dict(CITE)]
    p.update(recommended_status=status, reviewer_name="Donovan Example", reviewer_attests=True)
    return p


def test_template_contains_questions_not_claims():
    t = lr.build_template("US", "United States", "HI")
    assert t["reviewer_attests"] is False and t["drafted_by_ai"] is True
    for s in lr.SECTIONS:
        assert t["sections"][s]["text"] == "" and t["sections"][s]["questions"]
    ready, problems = lr.validate_packet(t, TODAY)
    assert not ready and problems


def test_complete_packet_is_ready_and_payload_keeps_sources():
    ok, problems = lr.validate_packet(good(), TODAY)
    assert ok and problems == []
    payload = lr.to_review_payload(good(), TODAY)
    assert payload["status"] == "active"
    assert "Sources:" in payload["disclosure_requirements"] and "Property Act s.12(3)" in payload["licensing_requirements"]
    assert payload["reviewed_by"].startswith("Donovan Example") and "AI assistance" in payload["reviewed_by"]


def test_uncited_finding_is_rejected():
    p = good()
    p["sections"]["licensing_requirements"]["citations"] = []
    ok, problems = lr.validate_packet(p, TODAY)
    assert not ok and any("citation is required" in x for x in problems)


def test_bad_citation_fields_rejected():
    p = good()
    p["sections"]["sanctions_notes"]["citations"] = [{"source": "", "reference": "x", "retrieved_on": "yesterday"}]
    _, problems = lr.validate_packet(p, TODAY)
    assert any("source is missing" in x for x in problems)
    assert any("specific reference" in x for x in problems)
    assert any("YYYY-MM-DD" in x for x in problems)
    p["sections"]["sanctions_notes"]["citations"] = [dict(CITE, retrieved_on="2027-01-01")]
    assert any("future" in x for x in lr.validate_packet(p, TODAY)[1])


def test_placeholder_and_short_text_rejected():
    p = good()
    p["sections"]["disclosure_requirements"]["text"] = "TBD pending the research on local statutes for this place"
    assert any("placeholder" in x for x in lr.validate_packet(p, TODAY)[1])
    p["sections"]["disclosure_requirements"]["text"] = "Short."
    assert any("at least" in x for x in lr.validate_packet(p, TODAY)[1])


@pytest.mark.parametrize("name", ["", "AI", "Claude", "SI system", "auto_reviewer", "ab"])
def test_non_human_or_blank_reviewer_rejected(name):
    p = good()
    p["reviewer_name"] = name
    ok, problems = lr.validate_packet(p, TODAY)
    assert not ok and any("reviewer_name" in x for x in problems)


def test_attestation_required():
    p = good()
    p["reviewer_attests"] = False
    assert not lr.validate_packet(p, TODAY)[0]


def test_active_needs_all_sections_restricted_needs_one():
    p = good("active")
    p["sections"]["sanctions_notes"] = {"text": "", "citations": []}
    assert not lr.validate_packet(p, TODAY)[0]
    p["recommended_status"] = "restricted"
    assert lr.validate_packet(p, TODAY)[0]
    assert lr.to_review_payload(p, TODAY)["sanctions_notes"] is None


def test_suspended_needs_reason_and_bad_status_rejected():
    p = lr.build_template("XX", "Exampleland")
    p.update(recommended_status="suspended", reviewer_name="Donovan Example", reviewer_attests=True)
    assert not lr.validate_packet(p, TODAY)[0]
    p["sections"]["sanctions_notes"]["text"] = "Sanctions imposed; suspended until the restriction is lifted."
    assert not lr.validate_packet(p, TODAY)[0]  # even a suspension reason must be cited
    p["sections"]["sanctions_notes"]["citations"] = [dict(CITE)]
    assert lr.validate_packet(p, TODAY)[0]
    p["recommended_status"] = "pending_review"
    assert not lr.validate_packet(p, TODAY)[0]


def test_payload_refused_when_not_ready():
    p = good()
    p["reviewer_attests"] = False
    with pytest.raises(ValueError):
        lr.to_review_payload(p, TODAY)
