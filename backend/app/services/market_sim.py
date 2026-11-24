"""
Market simulator / digital twin (PURE, standard library only).

Runs many synthetic auctions with a fixed random seed to estimate how the
platform's fee band performs BEFORE real listings depend on it. It models
bidder counts, bid levels against a reserve and the clearing price, then
applies the fee in exact whole cents using money.fee_minor.

This is a what-if tool for the architect. Its output is an estimate from
stated assumptions, never a forecast of real revenue and never recorded as
revenue anywhere: real revenue is only a bank-confirmed credit.
"""
import random
from typing import Dict, Iterable, List

from app.services import money


def _percentile(sorted_vals: List[int], p: float) -> int:
    if not sorted_vals:
        return 0
    k = min(len(sorted_vals) - 1, max(0, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def simulate(n_auctions: int, reserve_minor: int, seed: int = 11, mean_bidders: float = 3.0,
             bid_spread: float = 0.35, increment_minor: int = 100,
             fee_bps_list: Iterable[int] = (500, 650, 800)) -> dict:
    if not 1 <= n_auctions <= 20000:
        raise ValueError("n_auctions must be between 1 and 20000.")
    if reserve_minor <= 0:
        raise ValueError("reserve_minor must be positive.")
    fee_bps_list = list(fee_bps_list)
    rng = random.Random(seed)
    prices: List[int] = []
    for _ in range(n_auctions):
        bidders = max(0, int(round(rng.gauss(mean_bidders, 1.2))))
        bids = sorted((int(reserve_minor * rng.lognormvariate(0.1, bid_spread)) for _ in range(bidders)),
                      reverse=True)
        if not bids or bids[0] < reserve_minor:
            continue
        second = bids[1] if len(bids) > 1 else reserve_minor
        prices.append(min(bids[0], max(reserve_minor, second + increment_minor)))
    prices.sort()
    fees: Dict[int, int] = {bps: sum(money.fee_minor(p, bps) for p in prices) for bps in fee_bps_list}
    return {
        "assumptions": {"n_auctions": n_auctions, "reserve_minor": reserve_minor, "seed": seed,
                        "mean_bidders": mean_bidders, "bid_spread": bid_spread},
        "sold": len(prices),
        "sold_rate": round(len(prices) / n_auctions, 4),
        "price_p10_minor": _percentile(prices, 0.10),
        "price_p50_minor": _percentile(prices, 0.50),
        "price_p90_minor": _percentile(prices, 0.90),
        "estimated_fee_total_minor_by_bps": fees,
        "disclaimer": "Simulation under stated assumptions. Not a forecast and never recorded as revenue.",
    }
