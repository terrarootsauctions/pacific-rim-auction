"""
Portfolio bundling optimizer (PURE, standard library only).

Chooses which assets to bundle into a sale program to maximise expected fee
value, subject to a total-cost budget and a per-country cap. Small problems
are solved exactly; larger ones use simulated annealing (a classical,
quantum-inspired method) with a fixed random seed, so a given input always
gives the same answer. No quantum hardware or paid service is involved.

All money is whole minor units (integers).
"""
import math
import random
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Sequence

EXACT_LIMIT = 16


@dataclass(frozen=True)
class Item:
    id: str
    value_minor: int
    cost_minor: int
    country: str


def _feasible(chosen: Sequence[Item], budget_minor: int, per_country_cap: Optional[int]) -> bool:
    if sum(i.cost_minor for i in chosen) > budget_minor:
        return False
    if per_country_cap is not None:
        counts: Dict[str, int] = {}
        for i in chosen:
            counts[i.country] = counts.get(i.country, 0) + 1
            if counts[i.country] > per_country_cap:
                return False
    return True


def _exact(items: List[Item], budget: int, cap: Optional[int]) -> List[Item]:
    best, best_val = [], 0
    for r in range(1, len(items) + 1):
        for combo in combinations(items, r):
            if _feasible(combo, budget, cap):
                v = sum(i.value_minor for i in combo)
                if v > best_val:
                    best, best_val = list(combo), v
    return best


def _anneal(items: List[Item], budget: int, cap: Optional[int], seed: int, iterations: int) -> List[Item]:
    rng = random.Random(seed)
    n = len(items)
    state = [False] * n
    # greedy start: best value per cost first
    for idx in sorted(range(n), key=lambda i: -items[i].value_minor / max(items[i].cost_minor, 1)):
        trial = [items[j] for j in range(n) if state[j]] + [items[idx]]
        if _feasible(trial, budget, cap):
            state[idx] = True

    def value(s):
        return sum(items[i].value_minor for i in range(n) if s[i])

    def ok(s):
        return _feasible([items[i] for i in range(n) if s[i]], budget, cap)

    cur_val = value(state)
    best, best_val = state[:], cur_val
    t0 = max(max(i.value_minor for i in items), 1)
    for step in range(iterations):
        temp = t0 * (1 - step / iterations) + 1e-9
        cand = state[:]
        i = rng.randrange(n)
        cand[i] = not cand[i]
        if rng.random() < 0.5:  # swap move
            j = rng.randrange(n)
            cand[j] = not cand[j]
        if not ok(cand):
            continue
        cv = value(cand)
        delta = cv - cur_val
        if delta >= 0 or rng.random() < math.exp(delta / temp):
            state, cur_val = cand, cv
            if cur_val > best_val:
                best, best_val = state[:], cur_val
    return [items[i] for i in range(n) if best[i]]


def solve(items: List[Item], budget_minor: int, per_country_cap: Optional[int] = None,
          seed: int = 7, iterations: int = 20000) -> dict:
    if budget_minor < 0:
        raise ValueError("Budget cannot be negative.")
    for i in items:
        if i.value_minor < 0 or i.cost_minor < 0:
            raise ValueError("Values and costs must not be negative.")
    if not items:
        return {"method": "none", "chosen": [], "total_value_minor": 0, "total_cost_minor": 0}
    if len(items) <= EXACT_LIMIT:
        chosen, method = _exact(items, budget_minor, per_country_cap), "exact"
    else:
        chosen, method = _anneal(items, budget_minor, per_country_cap, seed, iterations), "annealing"
    return {
        "method": method,
        "chosen": [i.id for i in chosen],
        "total_value_minor": sum(i.value_minor for i in chosen),
        "total_cost_minor": sum(i.cost_minor for i in chosen),
    }
