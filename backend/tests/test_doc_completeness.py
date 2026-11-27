import re

import pytest

from app.services import doc_completeness as dc

DEED = ("WARRANTY DEED. Maile Kahale, Grantor, hereby conveys to Donovan Example, Grantee, the parcel at 12 Kauai Road, "
        "Lihue, TMK (4) 3-6-001-002. Signed /s/ Maile Kahale. Acknowledged before me, Notary Public. "
        "Recorded at the Bureau of Conveyances, Document No. 2024-123456.")


def test_complete_deed_finds_every_element_with_exact_words():
    out = dc.check_completeness("deed", DEED)
    assert out["all_present"] and out["missing"] == []
    flat = " ".join(DEED.split())
    for e in out["elements"]:
        assert e["status"] == "found" and e["quote"] in flat   # every quote is a real slice of the document


def test_missing_elements_are_reported_not_guessed():
    out = dc.check_completeness("deed", "Maile Kahale, Grantor, conveys to Donovan Example, Grantee, the lot described below.")
    assert not out["all_present"] and "notary acknowledgment" in out["missing"] and "recording information" in out["missing"]
    assert all(e["quote"] == "" for e in out["elements"] if e["status"] == "missing")


def test_never_claims_validity():
    out = dc.check_completeness("deed", DEED)
    assert "valid" not in " ".join(k for k in out) and "does not say the document is valid" in out["notice"]


def test_other_types_and_bad_input():
    assert dc.check_completeness("court_order", "In the Circuit Court, Case No. 1CC-24-0001234. It is so ordered. Dated 2024. Judge Smith")["all_present"]
    for args in (("lease", DEED), ("deed", ""), ("deed", "x" * 200001), ("deed", None)):
        with pytest.raises(dc.DocError):
            dc.check_completeness(*args)
