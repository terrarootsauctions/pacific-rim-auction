import json
from datetime import date

import pytest

from app.services import astra_draft as ad
from app.services import legal_review as lr

GOOD = {"sections": {
    "disclosure_requirements": {"text": "Sellers must disclose known defects to buyers before closing under the cited statute.", "citations": [{"source": "Example Gazette", "reference": "Property Act s.12(3)", "confidence": "high"}]},
    "licensing_requirements": {"text": "An auction house licence is required from the national trade authority.", "citations": [{"source": "Trade Authority", "reference": "https://example.gov/licences"}]},
    "sanctions_notes": {"text": "", "citations": []},
}, "extra": "ignored"}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status; self._b = body
    def json(self):
        if self._b is None: raise ValueError
        return self._b


def ok_post(content):
    return lambda url, headers, body, timeout: Resp(200, {"choices": [{"message": {"content": content}}]})


KW = dict(api_key="k", model="m")


def test_not_configured_fails_closed():
    for kw in ({"api_key": "", "model": "m"}, {"api_key": "k", "model": ""}):
        with pytest.raises(ad.AstraError):
            ad.draft_packet("XX", "Exampleland", None, post=ok_post("{}"), **kw)


def test_draft_leaves_every_human_field_blank():
    out = ad.draft_packet("XX", "Exampleland", None, post=ok_post(json.dumps(GOOD)), **KW)
    p = out["packet"]
    assert p["recommended_status"] is None and p["reviewer_name"] == "" and p["reviewer_attests"] is False
    assert all(c["retrieved_on"] == "" for s in lr.SECTIONS for c in p["sections"][s]["citations"])
    assert "confidence" not in p["sections"]["disclosure_requirements"]["citations"][0]
    assert "NOT VERIFIED" in out["notice"]


def test_a_draft_can_never_pass_validation_as_is():
    p = ad.draft_packet("XX", "Exampleland", None, post=ok_post(json.dumps(GOOD)), **KW)["packet"]
    ready, problems = lr.validate_packet(p, date(2026, 11, 26))
    assert not ready and any("retrieved_on" in x for x in problems) and any("reviewer" in x.lower() for x in problems)


def test_bad_provider_answers_raise_and_never_guess():
    for post in (lambda *a: Resp(500, {}), lambda *a: Resp(200, {"nope": 1}), ok_post("not json"), ok_post(json.dumps({"sections": {}})), ok_post(json.dumps({"sections": {s: {"text": "", "citations": []} for s in lr.SECTIONS}}))):
        with pytest.raises(ad.AstraError):
            ad.draft_packet("XX", "Exampleland", None, post=post, **KW)
    def boom(*a): raise TimeoutError()
    with pytest.raises(ad.AstraError):
        ad.draft_packet("XX", "Exampleland", None, post=boom, **KW)


def test_only_jurisdiction_names_are_sent():
    sent = {}
    def spy(url, headers, body, timeout):
        sent.update(url=url, body=body); return Resp(200, {"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    ad.draft_packet("US", "United States", "HI", post=spy, api_key="k", model="m")
    text = json.dumps(sent["body"])
    assert sent["url"].endswith("/chat/completions") and "United States" in text and "HI" in text
    assert "user" not in {m["role"] for m in sent["body"]["messages"] if m["content"].lower().startswith("email")}
