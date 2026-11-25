"""
OFAC sanctions screening - fail-closed.

Loads the official OFAC SDN list (SDN.CSV + ALT.CSV aliases) and screens
names against it. Anything uncertain blocks and escalates to a human:
  * list not loaded, older than MAX_AGE, or suspiciously small  -> BLOCK
  * no usable name to screen                                    -> BLOCK
  * exact name match (order-insensitive)                        -> BLOCK
  * possible match (one name's words contained in the other,
    both with 2+ words)                                         -> BLOCK, needs human review
It never clears a name it could not check. A screen is not a legal opinion:
OFAC's own guidance applies, and a human decides every possible match.

The download needs network access, so it runs on the deployed service, not
in the build workspace. The URLs are settings so they can be corrected
without a code change; /admin/tools/sanctions shows whether the load worked.
"""
import asyncio
import csv
import io
import re
import threading
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

MAX_AGE = timedelta(hours=72)
MIN_ENTRIES_SANITY = 1000      # the real SDN list has many thousands of rows
_NULL = "-0-"


def tokens(name: Optional[str]) -> frozenset:
    """Order-insensitive word set. 'SMITH, John' and 'John Smith' give the same set."""
    if not name:
        return frozenset()
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return frozenset(w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w)


class Screener:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: List[tuple] = []   # (token_set, ent_num, display_name, sdn_type, is_alias)
        self.loaded_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.last_attempt: Optional[datetime] = None

    # ---- loading ---------------------------------------------------------
    def load_csv(self, sdn_csv: str, alt_csv: str, now: datetime, min_entries: int = MIN_ENTRIES_SANITY) -> None:
        entries = []
        for row in csv.reader(io.StringIO(sdn_csv)):
            if len(row) < 3 or row[1].strip() in ("", _NULL):
                continue
            entries.append((tokens(row[1]), row[0].strip(), row[1].strip(), row[2].strip(), False))
        for row in csv.reader(io.StringIO(alt_csv)):
            if len(row) < 4 or row[3].strip() in ("", _NULL):
                continue
            entries.append((tokens(row[3]), row[0].strip(), row[3].strip(), "alias", True))
        entries = [e for e in entries if e[0]]
        if len(entries) < min_entries:
            raise ValueError(f"Sanctions list has only {len(entries)} usable entries; refusing to use it.")
        with self._lock:
            self._entries = entries
            self.loaded_at = now
            self.last_error = None

    def fetch(self, sdn_url: str, alt_url: str, now: Optional[datetime] = None) -> bool:
        import requests  # in requirements.txt
        now = now or datetime.utcnow()
        self.last_attempt = now
        try:
            texts = []
            for url in (sdn_url, alt_url):
                r = requests.get(url, timeout=60, headers={"User-Agent": "PacificRimAuctions-Screening/1.0"})
                r.raise_for_status()
                texts.append(r.content.decode("utf-8", errors="replace"))
            self.load_csv(texts[0], texts[1], now)
            return True
        except Exception as exc:  # keep any previously loaded list; staleness is checked on use
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            return False

    # ---- screening -------------------------------------------------------
    def status(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        age = (now - self.loaded_at) if self.loaded_at else None
        return {
            "loaded": self.loaded_at is not None, "entries": len(self._entries),
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "age_hours": round(age.total_seconds() / 3600, 1) if age else None,
            "stale": bool(age and age > MAX_AGE), "last_error": self.last_error,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
        }

    def screen(self, names: Iterable[Optional[str]], now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        if self.loaded_at is None:
            return {"clear": False, "reason": "SDN_LIST_NOT_LOADED", "matches": []}
        if now - self.loaded_at > MAX_AGE:
            return {"clear": False, "reason": "SDN_LIST_STALE", "matches": []}
        queries = [(n, tokens(n)) for n in names if n and n.strip()]
        queries = [(n, t) for n, t in queries if t and len("".join(t)) >= 3]
        if not queries:
            return {"clear": False, "reason": "NO_NAME_TO_SCREEN", "matches": []}
        exact, possible = [], []
        with self._lock:
            entries = self._entries
        for raw, q in queries:
            for et, ent, disp, typ, alias in entries:
                hit = {"screened_name": raw, "sdn_name": disp, "ent_num": ent, "sdn_type": typ, "alias": alias}
                if q == et:
                    exact.append({**hit, "kind": "EXACT"})
                elif len(q) >= 2 and len(et) >= 2 and (et <= q or q <= et):
                    possible.append({**hit, "kind": "POSSIBLE"})
        if exact:
            return {"clear": False, "reason": "SDN_EXACT_MATCH", "matches": exact[:5]}
        if possible:
            return {"clear": False, "reason": "SDN_POSSIBLE_MATCH_REVIEW", "matches": possible[:5]}
        return {"clear": True, "reason": "NO_MATCH", "matches": []}


SCREENER = Screener()


async def refresh_loop(stop: asyncio.Event, sdn_url: str, alt_url: str,
                       ok_interval_s: int = 6 * 3600, retry_interval_s: int = 900) -> None:
    """Keeps the list fresh. Runs only when screening is enabled."""
    while not stop.is_set():
        ok = await asyncio.to_thread(SCREENER.fetch, sdn_url, alt_url)
        try:
            await asyncio.wait_for(stop.wait(), timeout=ok_interval_s if ok else retry_interval_s)
        except asyncio.TimeoutError:
            pass
