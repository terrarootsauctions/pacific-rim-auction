"""
Multi-entity ledger consolidation (PURE, standard library only).

Takes journal rows (entity, account, debit, credit) and produces:
  - per-entity, per-account net balances (debit minus credit, whole cents)
  - a consolidated view where accounts whose code starts with INTERCO_ are
    eliminated (they should net to zero across the three entities)
  - a balance check (total debits must equal total credits)

It reads; it never posts. Nothing here changes a ledger entry.
"""
from typing import Dict, Iterable, Tuple

Row = Tuple[str, str, int, int]  # entity_code, account_code, debit_minor, credit_minor


def consolidate(rows: Iterable[Row]) -> dict:
    per_entity: Dict[str, Dict[str, int]] = {}
    total_debit = total_credit = 0
    for entity, account, debit, credit in rows:
        if not isinstance(debit, int) or not isinstance(credit, int):
            raise TypeError("Ledger amounts must be whole minor units (integers).")
        per_entity.setdefault(entity, {})
        per_entity[entity][account] = per_entity[entity].get(account, 0) + debit - credit
        total_debit += debit
        total_credit += credit

    consolidated: Dict[str, int] = {}
    interco_residual = 0
    for accounts in per_entity.values():
        for account, net in accounts.items():
            if account.startswith("INTERCO_"):
                interco_residual += net
            else:
                consolidated[account] = consolidated.get(account, 0) + net
    return {
        "per_entity": per_entity,
        "consolidated": consolidated,
        "intercompany_residual_minor": interco_residual,  # non-zero means the entities disagree
        "balanced": total_debit == total_credit,
        "total_debit_minor": total_debit,
        "total_credit_minor": total_credit,
    }
