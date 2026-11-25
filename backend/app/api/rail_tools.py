"""
Admin-only, READ-ONLY tools for the First Hawaiian Bank rail and the
platform pipeline. Nothing here moves money, posts a ledger entry or changes
a record. Every endpoint reports or validates.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.admin import require_admin
from app.core.database import get_db
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.core.config import get_settings
from app.services import sanctions
from app.services import (
    account_validation, fhb_rail, ledger_consolidation, pipeline_runner, workflow_graph,
)

router = APIRouter(prefix="/admin/tools", tags=["admin-tools"])


class IdentifiersIn(BaseModel):
    routing: Optional[str] = Field(default=None, max_length=9)
    iban: Optional[str] = Field(default=None, max_length=40)
    swift: Optional[str] = Field(default=None, max_length=11)


class Bai2In(BaseModel):
    text: str = Field(max_length=500_000)



@router.get("/cutoffs")
def cutoffs(admin: User = Depends(require_admin)):
    """Where the current moment sits against the bank's cut-off times (Hawaii time)."""
    return fhb_rail.cutoff_status()


@router.post("/validate-identifiers")
def validate_identifiers(body: IdentifiersIn, admin: User = Depends(require_admin)):
    """Format and checksum checks only. These do not prove an account exists or who owns it."""
    return account_validation.validate_identifiers(body.routing, body.iban, body.swift)


@router.post("/bai2-preview")
def bai2_preview(body: Bai2In, admin: User = Depends(require_admin)):
    """Read a BAI2 statement and list its credits. Nothing is posted or matched automatically."""
    try:
        return fhb_rail.parse_bai2(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/workflow")
def workflow(admin: User = Depends(require_admin)):
    """The platform pipeline as nodes and edges, with its soundness check."""
    g = workflow_graph.platform_pipeline()
    return {"graph": workflow_graph.describe(g), "problems": workflow_graph.validate(g, "registry_scan")}


@router.get("/pipeline")
def pipeline_open_assets(limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Where every non-final asset stands in the pipeline and what needs a human next. Read-only."""
    return pipeline_runner.open_assets(db, max(1, min(limit, 200)))


@router.get("/pass-report")
def pass_report_preview(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """What moved, stalled, completed or got blocked since the last saved pass. Preview only: saves nothing."""
    return pipeline_runner.run_pass(db, save=False)


@router.post("/pass-report/run")
def pass_report_run(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Same report, and saves this pass as the baseline for the next one. The only thing written
    is a snapshot row; no asset, listing, ledger entry or payment is touched."""
    return pipeline_runner.run_pass(db, save=True)


@router.get("/pipeline/{asset_id}")
def pipeline_position(asset_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """One asset's position in the pipeline, read from real records. Read-only: it never creates,
    approves, publishes or pays anything."""
    out = pipeline_runner.position(db, asset_id)
    if out["error"] == "registry_scan: Asset not found.":
        raise HTTPException(status_code=404, detail="Asset not found")
    return out


@router.get("/ledger-consolidated")
def ledger_consolidated(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Per-entity and consolidated ledger balances, read from the existing journal."""
    rows = [(e.entity_code, e.account_code, e.debit_minor, e.credit_minor)
            for e in db.query(LedgerEntry).all()]
    return ledger_consolidation.consolidate(rows)


class ScreenIn(BaseModel):
    names: list[str] = Field(min_length=1, max_length=20)


@router.get("/sanctions")
def sanctions_status(admin: User = Depends(require_admin)):
    """Is the OFAC list loaded, how old is it, and is screening switched on?"""
    return {**sanctions.SCREENER.status(), "enforcing": get_settings().sanctions_screening_enabled}


@router.post("/sanctions/refresh")
def sanctions_refresh(admin: User = Depends(require_admin)):
    """Fetch the official list now (works even while enforcement is off, so you can check it first)."""
    s = get_settings()
    ok = sanctions.SCREENER.fetch(s.ofac_sdn_csv_url, s.ofac_alt_csv_url)
    return {"refreshed": ok, **sanctions.SCREENER.status()}


@router.post("/sanctions/screen")
def sanctions_screen(body: ScreenIn, admin: User = Depends(require_admin)):
    """Screen names against the loaded list. Read-only; blocks when the list is missing or stale."""
    return sanctions.SCREENER.screen(body.names)
