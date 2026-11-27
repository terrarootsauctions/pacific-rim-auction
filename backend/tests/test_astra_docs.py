import json

import pytest

from app.services import astra_docs as ad
from app.services.astra_draft import AstraError

DOC = "Warranty deed. Grantor Maile Kahale conveys to Donovan Example the parcel at 12 Kauai Road, Lihue, Hawaii, in fee simple."
KW = dict(api_key="k", model="m")


class Resp:
    def __init__(self, status=200, body=None): self.status_code = status; self._b = body
    def json(self):
        if self._b is None: raise ValueError
        return self._b


def reply(results):
    c = json.dumps({"results": results})
    return lambda *a: Resp(200, {"choices": [{"message": {"content": c}}]})


def run(statements, results, **over):
    args = dict(document_text=DOC, statements=statements, confirm_send_to_provider=True, post=reply(results), **KW); args.update(over)
    return ad.check_document(**args)


def test_supported_with_real_quote_passes_through():
    out = run(["Grantor conveys 12 Kauai Road."], [{"index": 0, "verdict": "supported", "quote": "conveys to Donovan Example the parcel at 12 Kauai Road"}])
    assert out["findings"][0]["verdict"] == "supported"


def test_invented_quote_is_downgraded_to_unclear():
    f = run(["Seller owns the mineral rights."], [{"index": 0, "verdict": "supported", "quote": "including all mineral rights"}])["findings"][0]
    assert f["verdict"] == "unclear" and f["quote"] == "" and "not in the document" in f["note"]


def test_supported_without_quote_is_unclear():
    assert run(["x statement"], [{"index": 0, "verdict": "supported", "quote": ""}])["findings"][0]["verdict"] == "unclear"


def test_missing_and_unknown_verdicts_are_unclear():
    out = run(["a", "b"], [{"index": 0, "verdict": "approved!", "quote": ""}])["findings"]
    assert out[0]["verdict"] == "unclear" and out[1]["verdict"] == "unclear" and "no answer" in out[1]["note"]


def test_must_confirm_before_text_leaves_platform():
    called = []
    with pytest.raises(AstraError):
        run(["a"], [], confirm_send_to_provider=False, post=lambda *a: called.append(1))
    assert not called


def test_limits_and_config_fail_closed():
    for kw in ({"document_text": "short"}, {"document_text": "x" * 60001}, {"statements": []}, {"statements": ["a"] * 21}, {"statements": [""]}, {"api_key": ""}):
        with pytest.raises(AstraError):
            run(kw.get("statements", ["a"]), [], **{k: v for k, v in kw.items() if k != "statements"})


def test_provider_failures_raise():
    for post in (lambda *a: Resp(500, {}), lambda *a: Resp(200, {"x": 1}), lambda *a: Resp(200, {"choices": [{"message": {"content": "nope"}}]})):
        with pytest.raises(AstraError):
            run(["a"], [], post=post)
    def boom(*a): raise TimeoutError()
    with pytest.raises(AstraError):
        run(["a"], [], post=boom)
