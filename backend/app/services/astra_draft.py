"""
Astra legal drafting (the "AI may research and draft" step).

Uses the OpenAI Responses API with the model in ASTRA_MODEL (GPT-6 Astra: `gpt-6-astra`):
  * strict structured output (a JSON schema), so the answer shape cannot drift
  * live web search, so sources are looked up instead of recalled
  * reasoning effort set by ASTRA_REASONING_EFFORT (default high)

Advisory only, by construction:
  * The draft never sets a status, a reviewer, or the attestation. Those stay blank,
    so legal_review.validate_packet() rejects the packet until a named person adds them.
  * A URL citation is kept ONLY if the web search actually returned that URL. A URL the model
    typed from memory is dropped. Citations without a URL (a statute section, say) come from the
    model's own knowledge and are unverified.
  * `retrieved_on` is left blank: the reviewer opens each source, confirms it, then dates it.
  * Only the country code, name and region are sent. No user, listing, claim or payment data.
  * Not configured, a provider error, a refusal or an unusable answer raise AstraError. No guess.

Pure apart from the HTTP call, which is injectable for tests. Switching to a different or
newer model (for example a legal-specific configuration when OpenAI opens one) is a settings change.
"""
import json
from typing import Callable, Dict, List, Optional, Set, Tuple

from app.services import legal_review

MAX_TEXT = 4000
MAX_CITATIONS = 8
NOTICE = (
    "AI-DRAFTED, NOT VERIFIED. URL sources were returned by a live web search; citations without a URL come "
    "from the model's own knowledge. Claims can still be wrong. A named reviewer must open each source, confirm "
    "it supports the finding, enter the date they retrieved it, then set the recommended status, their name and "
    "the attestation before this can be submitted."
)

_CITATION = {"type": "object", "additionalProperties": False, "required": ["source", "reference"],
             "properties": {"source": {"type": "string"}, "reference": {"type": "string"}}}
_SECTION = {"type": "object", "additionalProperties": False, "required": ["text", "citations"],
            "properties": {"text": {"type": "string"}, "citations": {"type": "array", "items": _CITATION}}}
DRAFT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sections"],
                "properties": {"sections": {"type": "object", "additionalProperties": False,
                                            "required": list(legal_review.SECTIONS),
                                            "properties": {s: _SECTION for s in legal_review.SECTIONS}}}}


class AstraError(Exception):
    pass


def is_configured(api_key: str, model: str) -> bool:
    return bool((api_key or "").strip() and (model or "").strip())


def _default_post(url, headers, json_body, timeout):
    import requests
    return requests.post(url, headers=headers, json=json_body, timeout=timeout)


def _norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def call_responses(*, api_key: str, model: str, base_url: str, timeout: int, post: Callable, messages: List[dict],
                   schema_name: str, schema: dict, effort: str = "high", web_search: bool = False) -> Tuple[str, Set[str]]:
    """One Responses API call. Returns (answer_text, urls_the_web_search_returned)."""
    if not is_configured(api_key, model):
        raise AstraError("Astra is not configured (OPENAI_API_KEY and ASTRA_MODEL are required).")
    body = {"model": model, "input": messages, "reasoning": {"effort": effort},
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}}
    if web_search:
        body["tools"] = [{"type": "web_search"}]
    try:
        resp = post(base_url.rstrip("/") + "/responses",
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, body, timeout)
    except Exception as exc:  # network failure, timeout
        raise AstraError(f"Could not reach the model provider: {type(exc).__name__}.")
    if getattr(resp, "status_code", 0) != 200:
        raise AstraError(f"The model provider returned HTTP {getattr(resp, 'status_code', '?')}; nothing was produced.")
    try:
        data = resp.json()
        output = data["output"]
        if not isinstance(output, list):
            raise TypeError
    except (KeyError, TypeError, ValueError):
        raise AstraError("The model provider's reply was not in the expected format; nothing was produced.")
    if data.get("status") in ("failed", "incomplete", "cancelled"):
        raise AstraError(f"The model run did not finish (status: {data.get('status')}); nothing was produced.")
    texts: List[str] = []
    urls: Set[str] = set()
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "refusal":
                raise AstraError("The model declined this request; nothing was produced.")
            if c.get("type") == "output_text":
                texts.append(c.get("text") or "")
                for a in c.get("annotations") or []:
                    if isinstance(a, dict) and a.get("type") == "url_citation" and a.get("url"):
                        urls.add(_norm_url(a["url"]))
    text = "".join(texts).strip()
    if not text:
        raise AstraError("The model returned no answer; nothing was produced.")
    return text, urls


def build_messages(country_code: str, country_name: str, region_code: Optional[str], web_search: bool = True) -> List[dict]:
    template = legal_review.build_template(country_code, country_name, region_code)
    questions = {s: template["sections"][s]["questions"] for s in legal_review.SECTIONS}
    where = f"{country_name} ({country_code})" + (f", region {region_code}" if region_code else "")
    system = (
        "You are a legal research assistant drafting a jurisdiction review for a human attorney to verify. "
        "You are not giving legal advice and you cannot sign anything. "
        + ("Use web search to find the primary sources (statutes, regulations, official bodies) and cite the exact pages you used. " if web_search else "")
        + "State only what you can tie to a specific named source. Where law applies to the facts, say how; separate what a "
        "source actually holds from commentary; note rules that cut against operating here. If you are not sure of "
        "something, leave that section's text empty rather than guessing. Never invent a citation or a URL."
    )
    user = (
        f"Jurisdiction: {where}.\nActivity: an online marketplace and auction platform for real property and "
        "unclaimed, dormant or abandoned assets, settling to a U.S. bank.\nAnswer these questions per section:\n"
        + json.dumps(questions, indent=2)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_draft(content: str, visited_urls: Set[str]) -> Dict[str, dict]:
    """Keep only text + (source, reference) citations. A URL citation survives only if web search returned it."""
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
            if not (isinstance(c, dict) and isinstance(c.get("source"), str) and isinstance(c.get("reference"), str)):
                continue
            ref = c["reference"].strip()
            if ref.lower().startswith(("http://", "https://")) and _norm_url(ref) not in visited_urls:
                continue  # a URL the search never returned: treat as invented
            cites.append({"source": c["source"].strip()[:300], "reference": ref[:500], "retrieved_on": ""})
        out[s] = {"text": text.strip()[:MAX_TEXT], "citations": cites}
    if not any(v["text"] for v in out.values()):
        raise AstraError("The model returned no usable findings; nothing was drafted.")
    return out


def draft_packet(country_code: str, country_name: str, region_code: Optional[str], *, api_key: str, model: str,
                 base_url: str = "https://api.openai.com/v1", timeout: int = 120, effort: str = "high",
                 web_search: bool = True, post: Callable = _default_post) -> dict:
    text, urls = call_responses(api_key=api_key, model=model, base_url=base_url, timeout=timeout, post=post,
                                messages=build_messages(country_code, country_name, region_code, web_search),
                                schema_name="jurisdiction_draft", schema=DRAFT_SCHEMA, effort=effort, web_search=web_search)
    drafted = parse_draft(text, urls if web_search else set())
    packet = legal_review.build_template(country_code, country_name, region_code)
    for s in legal_review.SECTIONS:
        packet["sections"][s]["text"] = drafted[s]["text"]
        packet["sections"][s]["citations"] = drafted[s]["citations"]
    packet["drafted_by_ai"] = True
    packet["recommended_status"] = None
    packet["reviewer_name"] = ""
    packet["reviewer_attests"] = False
    return {"packet": packet, "notice": NOTICE, "model": model}
