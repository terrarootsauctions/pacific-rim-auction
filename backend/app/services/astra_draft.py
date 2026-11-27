"""
Astra legal drafting (the "AI may research and draft" step).

Asks an OpenAI model (GPT-6 Astra, set with ASTRA_MODEL) to DRAFT the legal research
packet for one jurisdiction. This is advisory only, by construction:

  * The draft never sets a status, a reviewer, or the attestation. Those stay blank,
    so legal_review.validate_packet() rejects the packet until a named person adds them.
  * The model cannot browse here, so every citation it offers is UNVERIFIED. The draft
    leaves `retrieved_on` blank on purpose. The reviewer must open each source, confirm
    it says what the draft claims, and only then enter the date they retrieved it.
  * Only the country code, country name and region are sent to OpenAI. No user, listing,
    claim or payment data ever leaves the platform through this module.
  * Not configured, a network error, or an unusable answer all raise AstraError.
    There is no fallback text and no guess.

Pure apart from the HTTP call, which is injectable for tests.
"""
import json
from typing import Callable, Dict, List, Optional

from app.services import legal_review

MAX_TEXT = 4000
MAX_CITATIONS = 8
NOTICE = (
    "AI-DRAFTED, NOT VERIFIED. Every citation below came from a model that could not look anything up. "
    "A named reviewer must open each source, confirm it supports the finding, enter the date they "
    "retrieved it, then set the recommended status, their name and the attestation before this can be submitted."
)


class AstraError(Exception):
    pass


def is_configured(api_key: str, model: str) -> bool:
    return bool((api_key or "").strip() and (model or "").strip())


def build_messages(country_code: str, country_name: str, region_code: Optional[str]) -> List[Dict[str, str]]:
    template = legal_review.build_template(country_code, country_name, region_code)
    questions = {s: template["sections"][s]["questions"] for s in legal_review.SECTIONS}
    where = f"{country_name} ({country_code})" + (f", region {region_code}" if region_code else "")
    system = (
        "You are a legal research assistant drafting a jurisdiction review for a human attorney to verify. "
        "You are not giving legal advice and you cannot sign anything. Rules: state only what you can tie to a "
        "specific named source (statute, regulation, official body, section number or URL). If you are not sure "
        "of something, leave that section's text empty rather than guessing. Never invent a citation. "
        "Reply with JSON only, in exactly this shape: "
        '{"sections": {"disclosure_requirements": {"text": str, "citations": [{"source": str, "reference": str}]}, '
        '"licensing_requirements": {...}, "sanctions_notes": {...}}}.'
    )
    user = (
        f"Jurisdiction: {where}.\nActivity: an online marketplace and auction platform for real property and "
        "unclaimed, dormant or abandoned assets, settling to a U.S. bank.\nAnswer these questions per section:\n"
        + json.dumps(questions, indent=2)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_draft(content: str) -> Dict[str, dict]:
    """Keep only text + (source, reference) citations from the model's JSON. Everything else is dropped."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        raise AstraError("The model did not return valid JSON; nothing was drafted.")
    sections = (data or {}).get("sections")
    if not isinstance(sections, dict):
        raise AstraError("The model's answer had no sections; nothing was drafted.")
    out: Dict[str, dict] = {}
    for s in legal_review.SECTIONS:
        raw = sections.get(s) if isinstance(sections.get(s), dict) else {}
        text = raw.get("text") if isinstance(raw.get("text"), str) else ""
        cites = []
        for c in (raw.get("citations") if isinstance(raw.get("citations"), list) else [])[:MAX_CITATIONS]:
            if isinstance(c, dict) and isinstance(c.get("source"), str) and isinstance(c.get("reference"), str):
                cites.append({"source": c["source"].strip()[:300], "reference": c["reference"].strip()[:500], "retrieved_on": ""})
        out[s] = {"text": text.strip()[:MAX_TEXT], "citations": cites}
    if not any(v["text"] for v in out.values()):
        raise AstraError("The model returned no usable findings; nothing was drafted.")
    return out


def _default_post(url, headers, json_body, timeout):
    import requests
    return requests.post(url, headers=headers, json=json_body, timeout=timeout)


def draft_packet(
    country_code: str,
    country_name: str,
    region_code: Optional[str],
    *,
    api_key: str,
    model: str,
    base_url: str = "https://api.openai.com/v1",
    timeout: int = 120,
    post: Callable = _default_post,
) -> dict:
    if not is_configured(api_key, model):
        raise AstraError("Astra is not configured (OPENAI_API_KEY and ASTRA_MODEL are required).")
    body = {"model": model, "messages": build_messages(country_code, country_name, region_code),
            "response_format": {"type": "json_object"}}
    try:
        resp = post(base_url.rstrip("/") + "/chat/completions",
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, body, timeout)
    except Exception as exc:  # network failure, timeout
        raise AstraError(f"Could not reach the model provider: {type(exc).__name__}.")
    if getattr(resp, "status_code", 0) != 200:
        raise AstraError(f"The model provider returned HTTP {getattr(resp, 'status_code', '?')}; nothing was drafted.")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise AstraError("The model provider's reply was not in the expected format; nothing was drafted.")
    drafted = parse_draft(content)
    packet = legal_review.build_template(country_code, country_name, region_code)
    for s in legal_review.SECTIONS:
        packet["sections"][s]["text"] = drafted[s]["text"]
        packet["sections"][s]["citations"] = drafted[s]["citations"]
    packet["drafted_by_ai"] = True
    packet["recommended_status"] = None
    packet["reviewer_name"] = ""
    packet["reviewer_attests"] = False
    return {"packet": packet, "notice": NOTICE, "model": model}
