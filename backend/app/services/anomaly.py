"""
Inbound traffic anomaly detection (PURE, standard library only).

Looks at recent bank-notification events and reports patterns worth a
human's attention. It REPORTS; it never blocks, deletes or acts. A genuine
credit is still decided only by the signed-notification check in
payments.py.

Findings:
  - bad_signature_rate: many recent notifications failed signature checks
  - volume_spike: this window has far more events than the usual window
  - amount_outlier: a single credit is far above the usual size
"""
from datetime import datetime, timedelta
from statistics import median
from typing import List, Tuple

# event = (received_at, amount_minor, signature_ok)
Event = Tuple[datetime, int, bool]


def detect(events: List[Event], now: datetime, window_minutes: int = 60,
           baseline_windows: int = 24, spike_factor: float = 5.0,
           min_spike_events: int = 10, bad_sig_threshold: float = 0.2,
           min_bad_sig_events: int = 5, outlier_factor: float = 10.0) -> List[dict]:
    findings: List[dict] = []
    win = timedelta(minutes=window_minutes)
    recent = [e for e in events if now - win < e[0] <= now]

    if len(recent) >= min_bad_sig_events:
        bad = sum(1 for e in recent if not e[2])
        if bad / len(recent) >= bad_sig_threshold:
            findings.append({"kind": "bad_signature_rate", "recent": len(recent), "failed": bad})

    counts = []
    for i in range(1, baseline_windows + 1):
        hi = now - win * i
        lo = hi - win
        counts.append(sum(1 for e in events if lo < e[0] <= hi))
    base = median(counts) if counts else 0
    if len(recent) >= min_spike_events and len(recent) > spike_factor * max(base, 1):
        findings.append({"kind": "volume_spike", "recent": len(recent), "baseline_median": base})

    past_amounts = [e[1] for e in events if e[0] <= now - win and e[2]]
    if past_amounts:
        typical = median(past_amounts)
        for e in recent:
            if e[2] and typical > 0 and e[1] > outlier_factor * typical:
                findings.append({"kind": "amount_outlier", "amount_minor": e[1], "typical_minor": int(typical)})
    return findings
