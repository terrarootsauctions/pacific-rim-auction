"""
Seeds the jurisdiction_nodes table using real ISO 3166-1 (countries) and
ISO 3166-2 (country subdivisions - states/provinces/regions) data via the
`pycountry` library.

This is intentionally NOT run automatically on app startup. Jurisdiction
data is too consequential to populate from a guess - this script pulls
from the actual international standard, not from memory, so the node
list reflects real countries and real subdivisions.

Note: ISO 3166-1 lists more entries than the platform's 190-country
operating target. Every entry is seeded as PENDING_REVIEW; only nodes that
pass real legal review become ACTIVE, so the platform only operates where
a review has actually been completed.

Usage (run by whoever has the deployed environment with internet access):
    pip install pycountry
    python -m app.scripts.seed_jurisdiction_nodes

All nodes are created in PENDING_REVIEW status. The structure existing
does not mean legal review is complete - see jurisdiction_node.py for why
that distinction is enforced at the compliance-check level, not just in
a comment.
"""
import sys

try:
    import pycountry
except ImportError:
    print(
        "pycountry is not installed. Run: pip install pycountry\n"
        "This script intentionally does not fall back to a hand-written "
        "country/region list - jurisdiction data must come from the real "
        "ISO 3166 standard, not from a guess."
    )
    sys.exit(1)

from app.core.database import Base, SessionLocal, engine
from app.models.jurisdiction_node import JurisdictionNode, NodeStatus


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    created = 0
    skipped = 0

    try:
        for country in pycountry.countries:
            country_code = country.alpha_2
            country_name = country.name

            subdivisions = list(pycountry.subdivisions.get(country_code=country_code) or [])

            if not subdivisions:
                # Countries with no ISO subdivisions get a single
                # country-level node rather than being skipped.
                exists = (
                    db.query(JurisdictionNode)
                    .filter(
                        JurisdictionNode.country_code == country_code,
                        JurisdictionNode.region_code.is_(None),
                    )
                    .first()
                )
                if exists:
                    skipped += 1
                    continue
                db.add(
                    JurisdictionNode(
                        country_code=country_code,
                        country_name=country_name,
                        status=NodeStatus.PENDING_REVIEW,
                    )
                )
                created += 1
                continue

            for sub in subdivisions:
                exists = (
                    db.query(JurisdictionNode)
                    .filter(
                        JurisdictionNode.country_code == country_code,
                        JurisdictionNode.region_code == sub.code,
                    )
                    .first()
                )
                if exists:
                    skipped += 1
                    continue
                db.add(
                    JurisdictionNode(
                        country_code=country_code,
                        country_name=country_name,
                        region_code=sub.code,
                        region_name=sub.name,
                        status=NodeStatus.PENDING_REVIEW,
                    )
                )
                created += 1

        db.commit()
        print(f"Done. Created {created} jurisdiction nodes, skipped {skipped} duplicates.")
        total = db.query(JurisdictionNode).count()
        print(f"Total nodes now in database: {total}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
