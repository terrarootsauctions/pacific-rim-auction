"""
Pass report (PURE, standard library only).

Compares where every open asset stands NOW with where it stood on the
previous pass, so the 24/7 cycle shows exactly what moved, what stalled and
what needs a person. It never acts on anything.

A stalled asset is not a failure. The pipeline reads live records on every
pass, so when an outside office reopens and its records update, the asset
simply moves on the next pass with no one re-triggering it. `stalled_passes`
counts how many passes in a row an asset has stopped at the same place, so a
long wait is visible instead of silent.

Snapshot format: {"assets": {asset_id: {"status", "stopped_at",
"stalled_passes", "revenue_confirmed"}}}
"""
from collections import Counter
from typing import Dict, List, Optional

PIPELINE_ORDER = [
    "registry_scan", "compliance_gate", "route_property", "terraroots_handoff",
    "valuation_listing", "listing_approval", "marketplace_close", "record_expected_fee", "done",
]
_RANK = {name: i for i, name in enumerate(PIPELINE_ORDER)}


def _rank(stopped_at: Optional[str]) -> int:
    return _RANK.get(stopped_at, -1)


def compare(previous: Optional[dict], positions: List[dict], truncated: bool = False) -> dict:
    prev: Dict[str, dict] = (previous or {}).get("assets", {})
    cur = {p["asset_id"]: p for p in positions}
    changes = {k: [] for k in (
        "new", "advanced", "completed", "blocked", "regressed", "stalled", "revenue_confirmed", "closed_out",
    )}
    snapshot: Dict[str, dict] = {}
    waiting = Counter()

    for aid, p in cur.items():
        status, stop = p["status"], p["stopped_at"]
        before = prev.get(aid)
        stalled_passes = 0

        if before is None:
            changes["new"].append(aid)
        elif status == "blocked":
            if before["status"] != "blocked":
                changes["blocked"].append(aid)
        elif before["status"] == "blocked":
            changes["advanced"].append(aid)  # a human cleared the block
        elif status == "completed":
            if before["status"] != "completed":
                changes["completed"].append(aid)
        else:
            rb, ra = _rank(before["stopped_at"]), _rank(stop)
            if ra > rb:
                changes["advanced"].append(aid)
            elif ra < rb:
                changes["regressed"].append(aid)  # needs a look: records moved backwards
            else:
                stalled_passes = int(before.get("stalled_passes", 0)) + 1
                changes["stalled"].append({
                    "asset_id": aid, "stopped_at": stop,
                    "next_action": p.get("next_action"), "stalled_passes": stalled_passes,
                })

        if p.get("revenue_confirmed") and not (before or {}).get("revenue_confirmed"):
            changes["revenue_confirmed"].append(aid)
        if status == "paused" and p.get("next_action"):
            waiting[p["next_action"]] += 1
        snapshot[aid] = {
            "status": status, "stopped_at": stop, "stalled_passes": stalled_passes,
            "revenue_confirmed": bool(p.get("revenue_confirmed")),
        }

    changes["closed_out"] = [aid for aid in prev if aid not in cur]  # sold, rejected or withdrawn since last pass
    return {
        "counts": {k: len(v) for k, v in changes.items()},
        "changes": changes,
        "waiting_by_action": dict(waiting.most_common()),
        "assets_in_pass": len(cur),
        "truncated": truncated,
        "first_pass": previous is None,
        "snapshot": {"assets": snapshot},
    }
