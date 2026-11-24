"""
First Hawaiian Bank rail tooling (PURE, standard library only).

Everything here READS or PLANS. Nothing here moves money: the platform is
receive-only, so there is no wire, ACH origination or transfer code, and the
sweep planner always returns execute=False.

  - parse_bai2: reads a BAI2 prior-day/intraday statement and returns the
    credits (type codes 100-399) for matching against payment references.
    Debits are counted, never itemised for action.
  - cutoff_status: where "now" sits against the bank's cut-off times in
    Hawaii time. The cut-off times are settings supplied by the architect
    (defaults 10:30 domestic, 14:30 foreign); confirm them with the bank.
    Weekends are closed; bank holidays are NOT modelled.
  - sweep_plan: shows what a zero-balance concentration of each entity's
    cleared balance into the master operating account would look like, as a
    report for the architect and the bank. It never executes.
"""
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

HST = ZoneInfo("Pacific/Honolulu")
DEFAULT_DOMESTIC_CUTOFF = time(10, 30)
DEFAULT_FOREIGN_CUTOFF = time(14, 30)

CREDIT_RANGE = range(100, 400)
DEBIT_RANGE = range(400, 700)


# --------------------------------------------------------------------------
# BAI2
# --------------------------------------------------------------------------

def _records(text: str) -> List[List[str]]:
    """Join 88 continuation lines onto the record above, then split fields."""
    lines: List[str] = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("88,") and lines:
            lines[-1] = lines[-1].rstrip("/") + "," + line[3:]
        else:
            lines.append(line)
    return [ln.rstrip("/").split(",") for ln in lines]


def _amount_minor(text: str) -> int:
    t = text.strip()
    if not t or not t.lstrip("+-").isdigit():
        raise ValueError(f"Bad BAI2 amount: {text!r}")
    return int(t)  # BAI2 amounts carry implied decimals: already minor units


def parse_bai2(text: str) -> dict:
    """Parse a BAI2 file. Raises ValueError on a structurally broken file."""
    recs = _records(text)
    if not recs or recs[0][0] != "01" or recs[-1][0] != "99":
        raise ValueError("Not a BAI2 file: must start with record 01 and end with 99.")
    account = None
    currency = "USD"
    credits: List[dict] = []
    debit_count = 0
    for r in recs:
        code = r[0]
        if code == "03" and len(r) > 2:
            account = r[1] or account
            currency = r[2] or currency
        elif code == "16":
            if len(r) < 4:
                raise ValueError("Transaction record 16 is too short.")
            type_code = int(r[1])
            amount = _amount_minor(r[2])
            funds = r[3]
            idx = 4
            if funds == "S":
                idx = 7
            elif funds == "V":
                idx = 6
            elif funds == "D":
                n = int(r[4]) if len(r) > 4 and r[4].isdigit() else 0
                idx = 5 + 2 * n
            bank_ref = r[idx] if len(r) > idx else ""
            customer_ref = r[idx + 1] if len(r) > idx + 1 else ""
            memo = ",".join(r[idx + 2:]) if len(r) > idx + 2 else ""
            if type_code in CREDIT_RANGE:
                credits.append({
                    "type_code": type_code,
                    "amount_minor": abs(amount),
                    "currency": currency,
                    "bank_reference": bank_ref.strip(),
                    "customer_reference": customer_ref.strip(),
                    "memo": memo.strip(),
                })
            elif type_code in DEBIT_RANGE:
                debit_count += 1
    return {
        "account_suffix": (account or "")[-4:],  # never echo the full account number
        "credit_count": len(credits),
        "credit_total_minor": sum(c["amount_minor"] for c in credits),
        "debit_count": debit_count,
        "credits": credits,
    }


# --------------------------------------------------------------------------
# Cut-off timing
# --------------------------------------------------------------------------

def _is_business_day(d: datetime) -> bool:
    return d.weekday() < 5


def _next_cutoff(now_hst: datetime, cutoff: time) -> datetime:
    day = now_hst
    candidate = day.replace(hour=cutoff.hour, minute=cutoff.minute, second=0, microsecond=0)
    while not _is_business_day(candidate) or candidate <= now_hst:
        candidate = (candidate + timedelta(days=1)).replace(
            hour=cutoff.hour, minute=cutoff.minute, second=0, microsecond=0)
    return candidate


def cutoff_status(now_utc: Optional[datetime] = None,
                  domestic: time = DEFAULT_DOMESTIC_CUTOFF,
                  foreign: time = DEFAULT_FOREIGN_CUTOFF) -> dict:
    now = (now_utc or datetime.now(ZoneInfo("UTC")))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    now_hst = now.astimezone(HST)
    out = {"now_hst": now_hst.isoformat(), "business_day": _is_business_day(now_hst)}
    for name, cut in (("domestic", domestic), ("foreign", foreign)):
        nxt = _next_cutoff(now_hst, cut)
        today_open = _is_business_day(now_hst) and now_hst.time() < cut
        out[name] = {
            "cutoff_hst": cut.strftime("%H:%M"),
            "open_now": today_open,
            "next_cutoff_hst": nxt.isoformat(),
            "minutes_until_next": int((nxt - now_hst).total_seconds() // 60),
        }
    out["note"] = "Weekends are treated as closed. Bank holidays are not modelled; confirm with the bank."
    return out


# --------------------------------------------------------------------------
# Concentration (sweep) planning: REPORT ONLY
# --------------------------------------------------------------------------

def sweep_plan(entity_balances_minor: Dict[str, int], master_account: str = "MASTER_OPERATING") -> dict:
    lines = []
    total = 0
    for entity, bal in sorted(entity_balances_minor.items()):
        if not isinstance(bal, int):
            raise TypeError("Balances must be whole minor units (integers).")
        if bal > 0:
            lines.append({"from": entity, "to": master_account, "amount_minor": bal})
            total += bal
    return {
        "execute": False,
        "reason": "Receive-only platform: this is a plan for the architect and the bank, never an instruction.",
        "lines": lines,
        "total_minor": total,
    }
