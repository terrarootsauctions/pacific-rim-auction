"""
Property lead engine - Pacific Rim Auctions' own version of what a property-data platform does for
onboarding: take raw records from any source (county open data, uploaded CSV, partner feeds),
clean them to one shape, remove duplicates, flag distress, score, filter, and hand the contactable
ones to outreach.

What this file does NOT contain is data. It makes no claim to know a property or owner that a
source has not supplied; every field comes from the record that was fed in, and nothing is guessed
or filled from elsewhere. Pure functions only (no network, no database) so every rule is testable.
"""
import csv
import hashlib
import io
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

MAX_BATCH = 5000

STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
    "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}
STATE_CODES = set(STATES.values())

_SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN",
           "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL", "HIGHWAY": "HWY", "PARKWAY": "PKWY", "TERRACE": "TER",
           "APARTMENT": "APT", "SUITE": "STE"}

# Column names seen in county files / CSVs -> the canonical field they mean.
ALIASES = {
    "owner_name": ["owner", "ownername", "owner_name", "name", "owner1", "taxpayer", "property_owner", "current_owner_name_1", "current_owner", "owner_name_1", "owner_1"],
    "address": ["address", "site_address", "situs", "situs_address", "property_address", "street_address", "location"],
    "mailing_address": ["mailing_address", "mail_address", "owner_address", "mailing"],
    "city": ["city", "site_city", "situs_city"],
    "state": ["state", "site_state", "st"],
    "zip": ["zip", "zipcode", "zip_code", "postal_code", "site_zip"],
    "county": ["county", "county_name"],
    "parcel_id": ["parcel", "parcel_id", "parcel_number", "apn", "pin", "tms", "folio", "property_code", "account", "account_number", "acct", "tmk"],
    "email": ["email", "owner_email", "e-mail", "email_address"],
    "phone": ["phone", "owner_phone", "telephone", "mobile", "phone_number"],
    "assessed_value": ["assessed_value", "value", "market_value", "total_value", "assessed"],
    "mortgage_balance": ["mortgage_balance", "loan_balance", "open_loan_balance", "mortgage"],
    "amount_owed": ["amount_owed", "taxes_owed", "delinquent_amount", "amount_due", "surplus_amount", "amount", "balance_due", "total_due", "total", "taxdue"],
    "property_type": ["property_type", "use_code", "land_use", "type"],
    "flags": ["flags", "distress", "distress_flags", "tags"],
}

DISTRESS_FLAGS = {
    "tax_delinquent": 25, "pre_foreclosure": 25, "probate": 20, "unclaimed_funds": 20, "code_violation": 10,
    "lien": 10, "vacant": 15, "claims_expired": 0, "absentee_owner": 10, "out_of_state_owner": 8, "high_equity": 12,
}
_FLAG_WORDS = {
    "tax_delinquent": ("tax delinquent", "delinquent tax", "tax_delinquent", "taxdelinquent", "delinquent"),
    "pre_foreclosure": ("pre-foreclosure", "pre_foreclosure", "preforeclosure", "foreclosure", "lis pendens", "nod"),
    "probate": ("probate", "deceased", "estate of"),
    "unclaimed_funds": ("unclaimed", "surplus", "excess proceeds", "escheat"),
    "code_violation": ("code violation", "code_violation", "violation"),
    "lien": ("lien",),
    "vacant": ("vacant", "abandoned"),
    "claims_expired": ("claims will not be accepted", "deadline for claims has expired", "claims deadline expired",
                       "claim deadline expired", "deadline expired", "claim period expired", "time to claim has expired"),
}
_TRUE = {"1", "true", "yes", "y", "t"}
_EMAIL = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.I)


def _s(v: Any) -> str:
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()


def normalize_state(v: Any) -> Optional[str]:
    t = _s(v).upper().rstrip(".")
    if t in STATE_CODES:
        return t
    return STATES.get(t)


def normalize_zip(v: Any) -> Optional[str]:
    m = re.match(r"^(\d{5})(?:[-\s]?\d{4})?$", _s(v))
    return m.group(1) if m else None


def normalize_address(v: Any) -> Optional[str]:
    t = re.sub(r"[.,#]", " ", _s(v).upper())
    words = [_SUFFIX.get(w, w) for w in t.split()]
    return " ".join(words) or None


def normalize_email(v: Any) -> Optional[str]:
    t = _s(v).lower()
    return t if _EMAIL.match(t) else None


def normalize_phone(v: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", _s(v))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return f"+1{digits}" if len(digits) == 10 else None


def to_number(v: Any) -> Optional[float]:
    t = re.sub(r"[,$\s]", "", _s(v))
    try:
        return float(t) if t else None
    except ValueError:
        return None


def map_columns(raw: Dict[str, Any], mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Rename a raw row's columns to canonical fields. `mapping` ({canonical: source_column}) wins
    over the built-in alias table."""
    lowered = {re.sub(r"[\s\-]+", "_", str(k).strip().lower()): v for k, v in raw.items()}
    out: Dict[str, Any] = {}
    for canon, aliases in ALIASES.items():
        if mapping and canon in mapping:
            key = re.sub(r"[\s\-]+", "_", mapping[canon].strip().lower())
            if key in lowered:
                out[canon] = lowered[key]
            continue
        for a in aliases:
            if a in lowered and _s(lowered[a]):
                out[canon] = lowered[a]
                break
    return out


def _flags_from(value: Any, raw_text: str) -> set:
    found = set()
    parts = value if isinstance(value, (list, tuple, set)) else re.split(r"[;,|]", _s(value))
    text = (" ".join(_s(p) for p in parts) + " " + raw_text).lower()
    for flag, words in _FLAG_WORDS.items():
        if any(w in text for w in words):
            found.add(flag)
    return found


def normalize_record(raw: Dict[str, Any], mapping: Optional[Dict[str, str]] = None) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (lead, None) or (None, reason). A record needs a street address or a parcel id to be
    a property at all."""
    if not isinstance(raw, dict):
        return None, "record is not an object"
    m = map_columns(raw, mapping)
    address = normalize_address(m.get("address"))
    parcel = _s(m.get("parcel_id")).upper() or None
    if not address and not parcel:
        return None, "no address or parcel id"
    state = normalize_state(m.get("state"))
    lead = {
        "owner_name": _s(m.get("owner_name")).title() or None,
        "address": address,
        "mailing_address": normalize_address(m.get("mailing_address")),
        "city": _s(m.get("city")).title() or None,
        "state": state,
        "zip": normalize_zip(m.get("zip")),
        "county": _s(m.get("county")).title() or None,
        "parcel_id": parcel,
        "email": normalize_email(m.get("email")),
        "phone": normalize_phone(m.get("phone")),
        "assessed_value": to_number(m.get("assessed_value")),
        "mortgage_balance": to_number(m.get("mortgage_balance")),
        "amount_owed": to_number(m.get("amount_owed")),
        "property_type": _s(m.get("property_type")).lower() or None,
    }
    flags = _flags_from(m.get("flags"), "")
    if lead["amount_owed"] and lead["amount_owed"] > 0 and "tax_delinquent" not in flags and "unclaimed_funds" not in flags:
        pass  # an amount alone does not say which kind; the source must say (flags column)
    mail = lead["mailing_address"]
    if mail and address and mail != address:
        flags.add("absentee_owner")
    mail_state = None
    if _s(m.get("mailing_address")):
        tail = re.findall(r"\b([A-Z]{2})\b(?:\s+\d{5})?\s*$", _s(m.get("mailing_address")).upper())
        mail_state = tail[-1] if tail and tail[-1] in STATE_CODES else None
    if mail_state and state and mail_state != state:
        flags.add("out_of_state_owner")
    av, mb = lead["assessed_value"], lead["mortgage_balance"]
    if av and mb is not None and av > 0 and (av - mb) / av >= 0.5:
        flags.add("high_equity")
    lead["flags"] = sorted(flags)
    lead["score"], _ = score_lead(lead)
    lead["dedupe_key"] = dedupe_key(lead)
    return lead, None


def dedupe_key(lead: dict) -> str:
    if lead.get("parcel_id"):
        basis = f"P|{lead.get('state') or ''}|{lead.get('county') or ''}|{lead['parcel_id']}"
    else:
        basis = f"A|{lead.get('address')}|{(lead.get('city') or '').upper()}|{lead.get('state') or ''}|{lead.get('zip') or ''}"
    return hashlib.sha1(basis.encode()).hexdigest()


def score_lead(lead: dict) -> Tuple[int, List[str]]:
    """0-100. Each reason is listed so a person can see why a lead ranks where it does."""
    score, why = 0, []
    for flag in lead.get("flags") or []:
        pts = DISTRESS_FLAGS.get(flag, 0)
        if pts:
            score += pts
            why.append(f"{flag} +{pts}")
    if lead.get("email"):
        score += 8
        why.append("has email +8")
    if lead.get("phone"):
        score += 5
        why.append("has phone +5")
    owed = lead.get("amount_owed") or 0
    if owed >= 10000:
        score += 10
        why.append("amount owed >= 10,000 +10")
    elif owed >= 1000:
        score += 5
        why.append("amount owed >= 1,000 +5")
    return min(score, 100), why


def merge_leads(old: dict, new: dict) -> dict:
    """Same property seen again: keep what is known, fill blanks from the new record, union the flags."""
    out = dict(old)
    a, b = old.get("amount_owed"), new.get("amount_owed")
    if a is not None or b is not None:
        out["amount_owed"] = max(x for x in (a, b) if x is not None)
    for k, v in new.items():
        if k in ("flags", "score", "dedupe_key", "amount_owed"):
            continue
        if v not in (None, "") and out.get(k) in (None, ""):
            out[k] = v
    flags = set(old.get("flags") or []) | set(new.get("flags") or [])
    if "claims_expired" not in (new.get("flags") or []):
        flags.discard("claims_expired")
    out["flags"] = sorted(flags)
    out["dedupe_key"] = old.get("dedupe_key") or new.get("dedupe_key")
    out["score"], _ = score_lead(out)
    return out


def normalize_batch(rows: Iterable[dict], mapping: Optional[Dict[str, str]] = None) -> Tuple[List[dict], List[dict]]:
    """Cleans a whole batch, drops repeats inside it (merging them), and reports every rejected row."""
    rows = list(rows)
    if len(rows) > MAX_BATCH:
        raise ValueError(f"Batch too large: {len(rows)} rows (max {MAX_BATCH}).")
    good: Dict[str, dict] = {}
    rejected: List[dict] = []
    for i, raw in enumerate(rows):
        lead, why = normalize_record(raw, mapping)
        if lead is None:
            rejected.append({"row": i, "reason": why})
            continue
        k = lead["dedupe_key"]
        if k in good:
            # the same property on several rows = several bills (years, installments): add them up
            amounts = [x for x in (good[k].get("amount_owed"), lead.get("amount_owed")) if x is not None]
            good[k] = merge_leads(good[k], lead)
            if amounts:
                good[k]["amount_owed"] = round(sum(amounts), 2)
                good[k]["score"], _ = score_lead(good[k])
        else:
            good[k] = lead
    return list(good.values()), rejected


def parse_csv(text: str) -> List[dict]:
    if not _s(text):
        raise ValueError("CSV is empty.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row.")
    rows = []
    for r in reader:
        rows.append(r)
        if len(rows) > MAX_BATCH:
            raise ValueError(f"Batch too large (max {MAX_BATCH} rows per import).")
    return rows


CSV_FIELDS = ["est_revenue", "owner_name", "address", "city", "state", "zip", "county", "parcel_id", "email", "phone",
              "assessed_value", "amount_owed", "property_type", "flags", "score", "status", "source"]


def to_csv(leads: Iterable[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for l in leads:
        row = dict(l)
        row["flags"] = ";".join(l.get("flags") or [])
        w.writerow(row)
    return buf.getvalue()


def matches(lead: dict, *, states=None, min_score: int = 0, all_flags=None, any_flags=None,
            has_email: bool = False, has_phone: bool = False, county: Optional[str] = None) -> bool:
    """List stacking: a lead must carry every flag in all_flags and at least one in any_flags."""
    flags = set(lead.get("flags") or [])
    if states and lead.get("state") not in {s.upper() for s in states}:
        return False
    if county and (lead.get("county") or "").lower() != county.lower():
        return False
    if (lead.get("score") or 0) < min_score:
        return False
    if all_flags and not set(all_flags) <= flags:
        return False
    if any_flags and not (set(any_flags) & flags):
        return False
    if has_email and not lead.get("email"):
        return False
    if has_phone and not lead.get("phone"):
        return False
    return True


def split_owner_name(owner: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(first, last, company). A name that looks like an entity goes to company, not split."""
    if not owner:
        return None, None, None
    if re.search(r"\b(LLC|INC|CORP|TRUST|LP|LTD|ESTATE|COMPANY|CO|BANK|ASSOCIATION)\b", owner.upper()):
        return None, None, owner
    parts = owner.split()
    if len(parts) == 1:
        return None, parts[0], None
    return parts[0], parts[-1], None


STAGE_B_RATE = 0.03   # low end of the 3-5% rolling scale on a marketplace closing


def revenue_estimate(lead: dict) -> dict:
    """What a lead could be worth to Pacific Rim, from the owner's stated revenue model - an ESTIMATE
    from the record's own numbers, not a forecast of what will close.
      stage_a: money held for the owner (amount_owed) - Stage A keeps 100% of proceeds.
      stage_b: a marketplace sale of the property - 3% of assessed value (low end of the 3-5% scale).
    'best' is the larger; 'basis' says which one it is."""
    fl = lead.get("flags") or []
    a = round(lead.get("amount_owed") or 0, 2) if ("unclaimed_funds" in fl and "claims_expired" not in fl) else 0.0
    b = round((lead.get("assessed_value") or 0) * STAGE_B_RATE, 2)
    return {"stage_a": a, "stage_b": b, "best": max(a, b), "basis": "stage_a" if a >= b and a > 0 else ("stage_b" if b > 0 else "none")}
