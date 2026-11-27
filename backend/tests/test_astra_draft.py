import json
from datetime import date

import pytest

from app.services import astra_draft as ad
from app.services import legal_review as lr

SEEN = "https://example.gov/licences"
GOOD = {"sections": {
    "disclosure_requirements": {"text": "Sellers must disclose known defects to buyers before closing under the cited statute.",
                                "citations": [{"source": "Example Gazette", "reference": "Property Act s.12(3)"}]},
    "licensing_requirements": {"text": "An auction house licence is required from the national trade authority.",
                               "citations": [{"source": "Trade Authority", "reference": SEEN},
                                             {"source": "Invented Site", "reference": "https://made-up.example/never-searched"}]},
    "sanctions_notes": {"text": "", "citations": []},
}}


class Resp:
    def __init__(self, status=200, body=None): self.status_code = status; self._b = body
    def json(self):
        if self._b is None: raise ValueError
        return self._b


def answer(content, urls=(SEEN,), status="completed"):
    ann = [{"type": "url_citation", "url": u, "title": "t"} for u in urls]
    return {"status": status, "output": [{"type": "web_search_call"}, {"type": "message", "content": [{"type": "output_text", "text": content, "annotations": ann}]}]}


def ok_post(content, **kw):
    return lambda url, headers, body, timeout: Resp(200, answer(content, **kw))


KW = dict(api_key="k", model="gpt-6-astra")


def test_not_configured_fails_closed():
    for kw in ({"api_key": "", "model": "m"}, {"api_key": "k", "model": ""}):
        with pytest.raises(ad.AstraError):
            ad.draft_packet("XX", "Exampleland", None, post=ok_post("{}"), **kw)


def test_request_uses_responses_api_with_search_schema_and_effort():
    sent = {}
    def spy(url, headers, body, timeout):
        sent.update(url=url, body=body); return Resp(200, answer(json.dumps(GOOD)))
    ad.draft_packet("US", "United States", "HI", post=spy, effort="max", **KW)
    b = sent["body"]
    assert sent["url"].endswith("/responses") and b["model"] == "gpt-6-astra"
    assert b["reasoning"] == {"effort": "max"} and {"type": "web_search"} in b["tools"]
    f = b["text"]["format"]
    assert f["type"] == "json_schema" and f["strict"] is True and f["schema"]["additionalProperties"] is False
    assert "United States" in json.dumps(b["input"]) and "HI" in json.dumps(b["input"])


def test_web_search_can_be_switched_off():
    sent = {}
    def spy(url, headers, body, timeout):
        sent.update(body=body); return Resp(200, answer(json.dumps(GOOD)))
    p = ad.draft_packet("XX", "Exampleland", None, post=spy, web_search=False, **KW)["packet"]
    assert "tools" not in sent["body"]
    # with no search, no URL can be verified, so URL citations are all dropped; statute text citations stay
    assert all(not c["reference"].startswith("http") for s in lr.SECTIONS for c in p["sections"][s]["citations"])


def test_url_citation_kept_only_if_search_returned_it():
    p = ad.draft_packet("XX", "Exampleland", None, post=ok_post(json.dumps(GOOD)), **KW)["packet"]
    refs = [c["reference"] for c in p["sections"]["licensing_requirements"]["citations"]]
    assert refs == [SEEN]
    assert p["sections"]["disclosure_requirements"]["citations"][0]["reference"] == "Property Act s.12(3)"


def test_draft_leaves_every_human_field_blank_and_cannot_pass_validation():
    out = ad.draft_packet("XX", "Exampleland", None, post=ok_post(json.dumps(GOOD)), **KW)
    p = out["packet"]
    assert p["recommended_status"] is None and p["reviewer_name"] == "" and p["reviewer_attests"] is False
    assert all(c["retrieved_on"] == "" for s in lr.SECTIONS for c in p["sections"][s]["citations"])
    ready, problems = lr.validate_packet(p, date(2026, 11, 26))
    assert not ready and any("retrieved_on" in x for x in problems) and any("reviewer" in x.lower() for x in problems)
    assert "NOT VERIFIED" in out["notice"]


def test_bad_provider_answers_raise_and_never_guess():
    empty = json.dumps({"sections": {s: {"text": "", "citations": []} for s in lr.SECTIONS}})
    refusal = {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}
    posts = (lambda *a: Resp(500, {}), lambda *a: Resp(200, {"nope": 1}), lambda *a: Resp(200, refusal),
             lambda *a: Resp(200, answer(json.dumps(GOOD), status="incomplete")), lambda *a: Resp(200, {"status": "completed", "output": []}),
             ok_post("not json"), ok_post(json.dumps({"sections": {}})), ok_post(empty))
    for post in posts:
        with pytest.raises(ad.AstraError):
            ad.draft_packet("XX", "Exampleland", None, post=post, **KW)
    def boom(*a): raise TimeoutError()
    with pytest.raises(ad.AstraError):
        ad.draft_packet("XX", "Exampleland", None, post=boom, **KW)
