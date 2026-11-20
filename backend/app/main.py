"""
Pacific Rim Auctions - headless API backend.

Entities served by this single codebase:
  - Pacific Rim Auctions (umbrella): sources/claims unclaimed, dormant, and
    abandoned assets and properties globally (all 9 asset categories);
    sets platform fee and compliance mandates (do no harm, follow the
    laws of the land)
  - Pacific Rim Auctions LLC: the real estate marketplace - residential,
    commercial, ultra-luxury, distressed, and foreclosure properties.
    Buyers and sellers meet and transact here directly; the platform has
    no legal ties to either party. Mandatory licensed property inspection,
    air quality assessment, and mineral rights disclosure before any
    listing goes live, fully disclosed to the buyer prior to closing.
    Charges a 3-5% rolling fee on closing costs. Also the direct
    marketplace for all non-real-property unclaimed asset categories.
  - TerraRoots Global Realty Solutions LLC: receives claimed real
    property from the umbrella and feeds it onto the Pacific Rim Auctions
    LLC marketplace to be listed and sold

Run locally:
    uvicorn app.main:app --reload

Interactive API docs (Swagger UI): http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, assets, audit_log, auth, bids, jurisdiction_nodes, listings, outreach, payments, si, users
from app.core.config import get_settings
from app.core.database import Base, engine

settings = get_settings()

# Creates tables if they don't exist yet. For production, prefer Alembic
# migrations - this is fine for getting the skeleton running immediately.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="Headless API for global unclaimed asset sourcing and the Pacific Rim "
    "Auctions LLC real estate marketplace, operating across 190 countries and six continents.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to known frontend origins before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(users.router, prefix=settings.api_v1_prefix)
app.include_router(assets.router, prefix=settings.api_v1_prefix)
app.include_router(listings.router, prefix=settings.api_v1_prefix)
app.include_router(bids.router, prefix=settings.api_v1_prefix)
app.include_router(payments.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(outreach.router, prefix=settings.api_v1_prefix)
app.include_router(si.router, prefix=settings.api_v1_prefix)
app.include_router(jurisdiction_nodes.router, prefix=settings.api_v1_prefix)
app.include_router(audit_log.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root():
    return {"name": settings.app_name, "status": "running"}


@app.get("/healthz")
def health_check():
    """Hit this URL to confirm the deployed service is actually alive."""
    return {"status": "ok"}
