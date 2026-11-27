"""
Document completeness check (our own code: no outside service, no key, no cost per use).

Same discipline as a good AI document review, done with plain rules:
  * Every "found" comes with the exact words from the document (a verbatim slice of the original).
  * Nothing is concluded beyond what the words show. This checks that required elements are PRESENT.
    It never says a document is valid, enforceable or sufficient; a person reads it and decides.
  * The element lists are working checklists to be confirmed by your attorney, not legal advice.

Pure (standard library only).
"""
import re
from typing import Dict, List, Optional

MAX_CHARS = 200000
NOTICE = ("PRESENCE CHECK ONLY. This shows which expected elements appear in the text, with the exact words. "
          "It does not say the document is valid or sufficient. The checklists are starting points for your "
          "attorney to confirm. Nothing was recorded or changed.")

# element name -> regex (case-insensitive). Add or edit elements here; no other code changes.
CHECKLISTS: Dict[str, Dict[str, str]] = {
    "deed": {
        "grantor named": r"\bgrantor\b|\bconveyed by\b|\bfrom\b[^.\n]{0,40}\bto\b",
        "grantee named": r"\bgrantee\b|\bconveys?\s+to\b|\bgrants?\s+to\b",
        "words of conveyance": r"\b(convey|conveys|conveyed|grant|grants|granted|transfer|transfers|warrant|warrants|quitclaim)\b",
        "property described": r"\b(parcel|lot\s+\d+|tmk|tax\s+map\s+key|legal\s+description|situate[d]?\s+at|located\s+at)\b",
        "signature": r"(/s/|\bsigned\b|\bsignature\b|in\s+witness\s+whereof)",
        "notary acknowledgment": r"\b(notary|notarial|acknowledged\s+before\s+me)\b",
        "recording information": r"\b(recorded|bureau\s+of\s+conveyances|document\s+no\.?|land\s+court|instrument\s+no\.?)\b",
    },
    "power_of_attorney": {
        "principal named": r"\bprincipal\b",
        "agent named": r"\b(agent|attorney[- ]in[- ]fact)\b",
        "powers granted": r"\b(power|powers|authority|authorize[sd]?)\b",
        "effective date": r"\b(effective|dated|as of)\b[^.\n]{0,40}\b(19|20)\d{2}\b",
        "signature": r"(/s/|\bsigned\b|\bsignature\b|in\s+witness\s+whereof)",
        "notary acknowledgment": r"\b(notary|notarial|acknowledged\s+before\s+me)\b",
    },
    "court_order": {
        "court named": r"\bcourt\b",
        "case number": r"\b(case|civil|docket|no\.?)\s*(no\.?|number|#)?\s*[:#]?\s*[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*",
        "ordering language": r"\b(ordered|adjudged|decreed|it\s+is\s+so\s+ordered)\b",
        "date": r"\b(19|20)\d{2}\b",
        "judge signature": r"(/s/|\bjudge\b|\bjustice\b|\bmagistrate\b)",
    },
    "claim_agreement": {
        "owner named": r"\b(owner|claimant|heir|beneficiary)\b",
        "asset described": r"\b(account|property|asset|parcel|funds|balance|holdings)\b",
        "authorization language": r"\b(authorize[sd]?|appoint[s]?|consent[s]?|agree[sd]?)\b",
        "signature": r"(/s/|\bsigned\b|\bsignature\b|in\s+witness\s+whereof)",
        "date": r"\b(19|20)\d{2}\b",
    },
}


class DocError(ValueError):
    pass


def _quote(text: str, m: "re.Match") -> str:
    start, end = max(0, m.start() - 60), min(len(text), m.end() + 60)
    return " ".join(text[start:end].split())


def check_completeness(doc_type: str, text: Optional[str]) -> dict:
    if doc_type not in CHECKLISTS:
        raise DocError(f"doc_type must be one of: {', '.join(sorted(CHECKLISTS))}.")
    if not isinstance(text, str) or len(text.strip()) < 20:
        raise DocError("document_text is required.")
    if len(text) > MAX_CHARS:
        raise DocError(f"document_text is over the {MAX_CHARS} character limit.")
    elements: List[dict] = []
    for name, pattern in CHECKLISTS[doc_type].items():
        m = re.search(pattern, text, re.I)
        elements.append({"element": name, "status": "found" if m else "missing", "quote": _quote(text, m) if m else ""})
    missing = [e["element"] for e in elements if e["status"] == "missing"]
    return {"doc_type": doc_type, "elements": elements, "missing": missing, "all_present": not missing, "notice": NOTICE}
