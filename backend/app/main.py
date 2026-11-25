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
    Charges a 5-8% rolling fee on closing costs. Also the direct
    marketplace for all non-real-property unclaimed asset categories.
  - TerraRoots Global Realty Solutions LLC: receives claimed real
    property from the umbrella and feeds it onto the Pacific Rim Auctions
    LLC marketplace to be listed and sold

Run locally:
    uvicorn app.main:app --reload

Interactive API docs (Swagger UI): http://localhost:8000/docs
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin, assets, audit_log, auth, bids, claims, crystal, entities, jurisdiction_nodes, lawful_basis, listings, memory,
    governance, legal_review, outreach, payments, rail_tools, reports, si, users, ws,
)
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.services import background, bootstrap, evolution, memory_lock

settings = get_settings()
log = logging.getLogger("pacific_rim")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Creates tables if they don't exist yet (Alembic migrations are a later step).
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        memory_lock.ensure_chain_head(db)
        db.commit()
        status = bootstrap.ensure_admin(db)
        if status:
            log.warning("[bootstrap] %s", status)
        evolution.get_params(db)
    stop = asyncio.Event()
    tasks = []
    if settings.background_enabled:
        tasks = [
            asyncio.create_task(background.close_loop(stop)),
            asyncio.create_task(background.verify_loop(stop)),
            asyncio.create_task(background.recheck_loop(stop)),
        ]
    try:
        yield
    finally:
        stop.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title=settings.app_name,
    description="Headless API for global unclaimed asset sourcing and the Pacific Rim "
    "Auctions LLC real estate marketplace, operating across 190 countries and six continents.",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(users.router, prefix=settings.api_v1_prefix)
app.include_router(assets.router, prefix=settings.api_v1_prefix)
app.include_router(claims.router, prefix=settings.api_v1_prefix)
app.include_router(reports.router, prefix=settings.api_v1_prefix)
app.include_router(lawful_basis.router, prefix=settings.api_v1_prefix)
app.include_router(entities.router, prefix=settings.api_v1_prefix)
app.include_router(listings.router, prefix=settings.api_v1_prefix)
app.include_router(bids.router, prefix=settings.api_v1_prefix)
app.include_router(payments.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(rail_tools.router, prefix=settings.api_v1_prefix)
app.include_router(governance.router, prefix=settings.api_v1_prefix)
app.include_router(outreach.router, prefix=settings.api_v1_prefix)
app.include_router(si.router, prefix=settings.api_v1_prefix)
app.include_router(jurisdiction_nodes.router, prefix=settings.api_v1_prefix)
app.include_router(legal_review.router, prefix=settings.api_v1_prefix)
app.include_router(audit_log.router, prefix=settings.api_v1_prefix)
app.include_router(memory.router, prefix=settings.api_v1_prefix)
app.include_router(ws.router)
app.include_router(crystal.router)


@app.get("/")
def root():
    return {"name": settings.app_name, "status": "running"}


@app.get("/healthz")
def health_check():
    """Hit this URL to confirm the deployed service is actually alive."""
    return {"status": "ok"}
