"""
Bank-identifier validation (PURE, standard library only).

Local format and checksum checks for the identifiers the platform handles:
  - ABA routing numbers (9 digits, weighted 3-7-1 checksum)
  - IBANs (ISO 13616 mod-97)
  - SWIFT/BIC codes (8 or 11 characters, ISO 9362 shape)

These catch typos and malformed identifiers before they reach a bank form.
They do NOT prove that an account exists or who owns it; beneficiary
ownership verification needs a bank or a verification provider. The platform
is receive-only, so this is used on identifiers shown to payers and on
inbound records, never to originate a payment.
"""
import re

_SWIFT = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


def aba_checksum_ok(routing: str) -> bool:
    if not isinstance(routing, str) or len(routing) != 9 or not routing.isdigit():
        return False
    d = [int(c) for c in routing]
    total = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])
    return total % 10 == 0


def iban_ok(iban: str) -> bool:
    if not isinstance(iban, str):
        return False
    s = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def swift_format_ok(bic: str) -> bool:
    return isinstance(bic, str) and bool(_SWIFT.fullmatch(bic.strip().upper()))


def validate_identifiers(routing: str = None, iban: str = None, swift: str = None) -> dict:
    """Returns {field: {"value_checked": bool, "ok": bool}} for each supplied
    identifier. Empty or omitted fields are skipped."""
    out = {}
    if routing:
        out["routing"] = {"ok": aba_checksum_ok(routing.strip())}
    if iban:
        out["iban"] = {"ok": iban_ok(iban)}
    if swift:
        out["swift"] = {"ok": swift_format_ok(swift)}
    return out
