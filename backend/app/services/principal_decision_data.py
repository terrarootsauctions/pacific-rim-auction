"""Pure data + rule for recorded Principal country-clearance decisions.
Kept free of database imports so it can be tested anywhere. Only decisions
the Principal made in his own words belong here, with the verbatim text."""

PRINCIPAL = "Donovan Vanaman"

DECISIONS = [
    {
        "country_code": "US",
        "region_code": "HI",
        "text": "I clear Hawaii/US.",
        "decided_on": "2026-11-25",
        "record": "docs/governance/decisions/2026-11-25_US-HI_clearance.md",
    },
]


def should_apply(status_value: str) -> bool:
    """Only a node still waiting for review is opened by a recorded decision."""
    return status_value == "pending_review"
