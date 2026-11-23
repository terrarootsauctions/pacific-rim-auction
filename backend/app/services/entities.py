"""
The three separate entities (PURE, no database). They are never merged:

  pacific_rim_auctions  umbrella: sources and claims unclaimed property in
                        every industry and runs the banking rails.
  terraroots            TerraRoots Global Realty Solutions LLC: auctions the
                        physical properties the umbrella hands to it.
  pacific_rim_auctions_llc  the marketplace for buying and selling properties;
                        earns the 5-8% rolling commission.

Pacific Rim Coin Exchange is a different company and is not part of this.
"""
UMBRELLA = "pacific_rim_auctions"
TERRAROOTS = "terraroots"
MARKETPLACE = "pacific_rim_auctions_llc"

ENTITIES = frozenset({UMBRELLA, TERRAROOTS, MARKETPLACE})
EXCLUDED_NAMES = frozenset({"pacific_rim_coin_exchange", "coin_exchange"})


def validate_handoff(from_entity: str, to_entity: str, reference: str = "") -> str:
    """A handoff moves an asset between two different entities of this
    platform. Returns the cleaned note. Raises ValueError otherwise."""
    for name in (from_entity, to_entity):
        if name in EXCLUDED_NAMES:
            raise ValueError("Pacific Rim Coin Exchange is not part of this platform.")
        if name not in ENTITIES:
            raise ValueError(f"Unknown entity '{name}'.")
    if from_entity == to_entity:
        raise ValueError("A handoff must go between two different entities.")
    return (reference or "").strip()


def entity_for_listing(latest_handoff_to):
    """Entity that runs a listing: the latest handoff target, else the
    marketplace."""
    return latest_handoff_to or MARKETPLACE
