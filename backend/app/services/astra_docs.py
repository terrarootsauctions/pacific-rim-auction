"""
Astra document checking: does this document actually support these statements?

Example: a seller says "I hold title to 12 Kaua'i Road" and uploads the deed text.
Astra reads the text and, for each statement, answers supported / not_supported / unclear.

Guards (so a wrong model answer cannot clear anything):
  * ADVISORY ONLY. Returns findings for a person; it never sets seller_holds_title,
    never records a lawful basis, never changes any record.
  * "supported" must carry a quote, and the quote must appear word-for-word in the
    document. Checked HERE, not trusted from the model; otherwise it is downgraded to "unclear".
  * Any statement the model skips is "unclear".
  * The caller must pass confirm_send_to_provider=True, because the document text leaves
    the platform. Size limits apply. Not configured or provider failure raises AstraError.
"""
import json
import re
from typing import Callable, Dict, List

from app.services.astra_draft import AstraError, _default_post, is_configured

class RequestError(AstraError):
    """The caller's request was wrong (HTTP 422), as opposed to a provider failure (502)."""


MAX_DOC_CHARS = 60000
MAX_STATEMENTS = 20
MAX_STATEMENT_CHARS = 500
VERDICTS = ("supported", "not_supported", "unclear")
NOTICE = ("AI-ASSISTED, NOT A DECISION. A named reviewer must read the quoted passages in the original "
          "document before relying on any finding. Nothing was recorded or changed.")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def validate_request(document_text, statements, confirm_send_to_provider) -> List[str]:
    if confirm_send_to_provider is not True:
        raise RequestError("confirm_send_to_provider must be true: the document text is sent to the AI provider.")
    if not isinstance(document_text, str) or len(document_text.strip()) < 20:
        raise RequestError("document_text is required.")
    if len(document_text) > MAX_DOC_CHARS:
        raise RequestError(f"document_text is over the {MAX_DOC_CHARS} character limit.")
    if not isinstance(statements, list) or not statements or len(statements) > MAX_STATEMENTS:
        raise RequestError(f"Provide 1 to {MAX_STATEMENTS} statements to check.")
    out = []
    for s in statements:
        if not isinstance(s, str) or not s.strip() or len(s) > MAX_STATEMENT_CHARS:
            raise RequestError(f"Each statement must be 1 to {MAX_STATEMENT_CHARS} characters of text.")
        out.append(s.strip())
    return out


def build_messages(document_text: str, statements: List[str]) -> List[Dict[str, str]]:
    system = (
        "You check whether a document supports statements. Use ONLY the document text provided. For each statement "
        "answer one of: supported, not_supported, unclear. 'supported' requires an exact quote copied word for word "
        "from the document. If the document does not clearly say it, answer unclear. Do not use outside knowledge. "
        'Reply with JSON only: {"results": [{"index": int, "verdict": str, "quote": str}]} with index starting at 0.'
    )
    user = "DOCUMENT:\n" + document_text + "\n\nSTATEMENTS:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(statements))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def verify_results(content: str, document_text: str, statements: List[str]) -> List[dict]:
    try:
        data = json.loads(content)
        raw = data["results"]
        if not isinstance(raw, list):
            raise TypeError
    except (TypeError, ValueError, KeyError):
        raise AstraError("The model's answer was not usable; nothing was checked.")
    by_index = {}
    for r in raw:
        if isinstance(r, dict) and isinstance(r.get("index"), int) and 0 <= r["index"] < len(statements):
            by_index.setdefault(r["index"], r)
    doc = _norm(document_text)
    findings = []
    for i, st in enumerate(statements):
        r = by_index.get(i) or {}
        verdict = r.get("verdict") if r.get("verdict") in VERDICTS else "unclear"
        quote = r.get("quote") if isinstance(r.get("quote"), str) else ""
        note = ""
        if verdict == "supported":
            if not _norm(quote) or _norm(quote) not in doc:
                verdict, quote, note = "unclear", "", "The model claimed support but its quote is not in the document."
        elif verdict != "supported":
            quote = quote if _norm(quote) in doc and _norm(quote) else ""
        if i not in by_index:
            note = "The model gave no answer for this statement."
        findings.append({"index": i, "statement": st, "verdict": verdict, "quote": quote, "note": note})
    return findings


def check_document(document_text, statements, confirm_send_to_provider, *, api_key, model,
                   base_url="https://api.openai.com/v1", timeout=120, post: Callable = _default_post) -> dict:
    if not is_configured(api_key, model):
        raise AstraError("Astra is not configured (OPENAI_API_KEY and ASTRA_MODEL are required).")
    sts = validate_request(document_text, statements, confirm_send_to_provider)
    body = {"model": model, "messages": build_messages(document_text, sts), "response_format": {"type": "json_object"}}
    try:
        resp = post(base_url.rstrip("/") + "/chat/completions",
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, body, timeout)
    except Exception as exc:
        raise AstraError(f"Could not reach the model provider: {type(exc).__name__}.")
    if getattr(resp, "status_code", 0) != 200:
        raise AstraError(f"The model provider returned HTTP {getattr(resp, 'status_code', '?')}; nothing was checked.")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise AstraError("The model provider's reply was not in the expected format; nothing was checked.")
    return {"findings": verify_results(content, document_text, sts), "notice": NOTICE, "model": model}
