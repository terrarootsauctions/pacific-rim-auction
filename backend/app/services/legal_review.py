"""
Legal review packets (PURE, standard library only).

This is the "Follow the Laws of the Land" mandate written as code. A
jurisdiction can only be cleared (node ACTIVE/RESTRICTED/SUSPENDED) through
the review endpoint, and this module defines what a review must contain
before that step is allowed to be taken:

  - AI MAY research and draft. It cannot sign.
  - Every finding must carry at least one citation: a named source, a
    specific reference (statute, section, URL or document) and the date it
    was retrieved. An uncited claim is rejected.
  - No placeholders: text such as "TBD", "TODO", "unverified" or "lorem" is
    rejected, so a blank or filler finding can never clear a country.
  - ONE named person attests to the review (the architect or a compliance
    officer). A reviewer name that is an AI or system label is rejected.
  - ACTIVE needs all three sections complete. RESTRICTED needs at least one.
    SUSPENDED needs a stated reason.

The template contains only QUESTIONS to research. It never contains an
assertion about what any country's law says: those come from cited sources.
Nothing here touches the database; the finished packet is turned into the
payload for the existing PATCH /jurisdiction-nodes/{id}/review endpoint.
"""
import re
from datetime import date
from typing import List, Optional, Tuple

SECTIONS = ("disclosure_requirements", "licensing_requirements", "sanctions_notes")

QUESTIONS = {
    "disclosure_requirements": [
        "What must a seller or marketplace disclose to a buyer of real property or other assets here?",
        "Are inspection, environmental or mineral-rights disclosures required before closing?",
        "What notice or claim procedure applies to unclaimed, dormant or abandoned property?",
        "Is there a cap or rule on finder, locator or recovery fees for unclaimed property?",
    ],
    "licensing_requirements": [
        "Is a license or registration needed to run an auction, brokerage or marketplace here?",
        "Are there restrictions on foreign or non-resident buyers or sellers?",
        "What data-protection or consumer-protection law applies to the platform's users?",
    ],
    "sanctions_notes": [
        "Is the country or region subject to sanctions or export restrictions?",
        "Which screening lists must be checked, and how often?",
        "Are there local rules on payments, currency or tax that limit settlement to a U.S. bank?",
    ],
}

NON_HUMAN_NAMES = frozenset({
    "ai", "si", "bot", "system", "auto", "automatic", "claude", "gpt", "assistant", "agent", "robot", "llm",
})
PLACEHOLDER = re.compile(r"\b(tbd|todo|to be determined|unverified|placeholder|lorem|n/?a|fill in)\b", re.I)
MIN_TEXT = 40
STATUSES = ("active", "restricted", "suspended")


def build_template(country_code: str, country_name: str, region_code: Optional[str] = None) -> dict:
    """An empty packet with the questions to research. Contains no legal claims."""
    return {
        "jurisdiction": {"country_code": country_code, "country_name": country_name, "region_code": region_code},
        "drafted_by_ai": True,
        "sections": {s: {"text": "", "citations": [], "questions": QUESTIONS[s]} for s in SECTIONS},
        "recommended_status": None,
        "reviewer_name": "",
        "reviewer_attests": False,
        "mandate_checks": {
            "do_no_harm": "Could listing or selling in this jurisdiction harm people, communities or the environment?",
            "follow_the_laws": "Does the cited research show the platform can operate here lawfully?",
        },
    }


def _citation_problems(label: str, citations, today: date) -> List[str]:
    out: List[str] = []
    if not citations:
        return [f"{label}: at least one citation is required."]
    for n, c in enumerate(citations, 1):
        c = c or {}
        if len((c.get("source") or "").strip()) < 2:
            out.append(f"{label} citation {n}: source is missing.")
        if len((c.get("reference") or "").strip()) < 3:
            out.append(f"{label} citation {n}: a specific reference (statute, section or URL) is required.")
        try:
            retrieved = date.fromisoformat((c.get("retrieved_on") or "").strip())
            if retrieved > today:
                out.append(f"{label} citation {n}: retrieved_on is in the future.")
        except ValueError:
            out.append(f"{label} citation {n}: retrieved_on must be a date (YYYY-MM-DD).")
    return out


def _section_complete(label: str, section: dict, today: date) -> Tuple[bool, List[str]]:
    text = ((section or {}).get("text") or "").strip()
    problems: List[str] = []
    if len(text) < MIN_TEXT:
        problems.append(f"{label}: the finding needs at least {MIN_TEXT} characters of real content.")
    elif PLACEHOLDER.search(text):
        problems.append(f"{label}: placeholder wording is not accepted.")
    problems += _citation_problems(label, (section or {}).get("citations"), today)
    return (not problems), problems


def validate_packet(packet: dict, today: Optional[date] = None) -> Tuple[bool, List[str]]:
    """Return (ready, problems). `ready` means the packet may be submitted to
    the review endpoint. It does not mean the findings are legally correct;
    that is what the named reviewer attests to."""
    today = today or date.today()
    problems: List[str] = []
    status = (packet.get("recommended_status") or "").lower()
    if status not in STATUSES:
        problems.append(f"recommended_status must be one of {', '.join(STATUSES)}.")

    reviewer = (packet.get("reviewer_name") or "").strip()
    if len(reviewer) < 3 or any(w in NON_HUMAN_NAMES for w in re.split(r"[\s_\-]+", reviewer.lower())):
        problems.append("reviewer_name must be the name of the person who reviewed this (not an AI or system label).")
    if packet.get("reviewer_attests") is not True:
        problems.append("The reviewer must attest that they reviewed the cited sources.")

    sections = packet.get("sections") or {}
    complete = 0
    for s in SECTIONS:
        ok, sec_problems = _section_complete(s, sections.get(s), today)
        if ok:
            complete += 1
        elif status == "active" or (sections.get(s) or {}).get("text"):
            problems += sec_problems
    if status == "active" and complete < len(SECTIONS):
        problems.append("ACTIVE requires all three sections complete and cited.")
    if status == "restricted" and complete < 1:
        problems.append("RESTRICTED requires at least one complete, cited section.")
    if status == "suspended" and not any(((sections.get(s) or {}).get("text") or "").strip() for s in SECTIONS):
        problems.append("SUSPENDED requires a stated reason in at least one section.")
    return (not problems), problems


def _with_sources(section: dict) -> Optional[str]:
    text = ((section or {}).get("text") or "").strip()
    if not text:
        return None
    cites = "\n".join(
        f"- {c['source'].strip()}, {c['reference'].strip()} (retrieved {c['retrieved_on'].strip()})"
        for c in (section.get("citations") or [])
    )
    return f"{text}\n\nSources:\n{cites}" if cites else text


def to_review_payload(packet: dict, today: Optional[date] = None) -> dict:
    """Turn a READY packet into the body for PATCH /jurisdiction-nodes/{id}/review.
    The citations are kept inside each text field, so they persist in the
    existing record with no schema change."""
    ready, problems = validate_packet(packet, today)
    if not ready:
        raise ValueError("Packet is not ready: " + " ".join(problems))
    sections = packet["sections"]
    reviewer = packet["reviewer_name"].strip()
    note = " (research drafted with AI assistance)" if packet.get("drafted_by_ai") else ""
    return {
        "status": packet["recommended_status"].lower(),
        "disclosure_requirements": _with_sources(sections.get("disclosure_requirements")),
        "licensing_requirements": _with_sources(sections.get("licensing_requirements")),
        "sanctions_notes": _with_sources(sections.get("sanctions_notes")),
        "reviewed_by": reviewer + note,
    }
