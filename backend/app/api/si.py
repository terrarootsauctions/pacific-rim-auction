from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.services import follow_the_sun, resilience, si_orchestrator

router = APIRouter(prefix="/si", tags=["si-orchestrator"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/briefing")
def get_architect_briefing(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """The full SI report for the human architect: system health, stalled
    assets, pending inspections, and real revenue - all in one call.
    Nothing here is auto-applied; this is information only."""
    return si_orchestrator.full_architect_briefing(db)


@router.get("/health")
def get_system_health(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return si_orchestrator.system_health_report(db)


@router.get("/stalled-assets")
def get_stalled_assets(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return si_orchestrator.stalled_assets_report(db)


@router.get("/pending-inspections")
def get_pending_inspections(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return si_orchestrator.pending_inspection_report(db)


@router.get("/follow-the-sun")
def get_follow_the_sun(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Which legally cleared countries are in daytime right now, which are
    asleep and when they wake. Only ACTIVE (reviewed) countries are counted."""
    try:
        return follow_the_sun.follow_the_sun_report(db)
    except follow_the_sun.TimeZoneDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/resilience")
def get_resilience(admin: User = Depends(require_admin)):
    """State of every circuit breaker (closed = healthy, open = a service is
    failing and calls are paused, half_open = testing recovery)."""
    return resilience.all_snapshots()
