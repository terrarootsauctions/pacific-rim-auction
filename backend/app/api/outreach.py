from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.outreach import OutreachContactCreate
from app.services import outreach

router = APIRouter(prefix="/outreach", tags=["outreach"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/verify")
def verify_reply_io_connection(admin: User = Depends(require_admin)):
    """Confirms the Reply.io API key actually works, by actually calling
    Reply.io - not a hardcoded success message."""
    try:
        return outreach.verify_credentials()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io verification failed: {exc}")


@router.post("/contacts", status_code=201)
def add_outreach_contact(
    contact_in: OutreachContactCreate,
    admin: User = Depends(require_admin),
):
    """Add a contact for outreach (potential seller, agent/broker, or
    a buyer to follow up with) and enroll them in the specified real
    Reply.io campaign."""
    try:
        contact = outreach.add_contact(
            email=contact_in.email,
            first_name=contact_in.first_name,
            last_name=contact_in.last_name,
            company=contact_in.company,
            country=contact_in.country,
            custom_fields={"campaign_type": contact_in.campaign_type.value},
        )
        enrollment = outreach.add_contact_to_campaign(
            contact_id=contact["id"], campaign_id=contact_in.campaign_id
        )
        return {"contact": contact, "enrollment": enrollment}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")


@router.get("/campaigns/{campaign_id}/stats")
def get_campaign_stats(campaign_id: str, admin: User = Depends(require_admin)):
    """Real send/open/reply numbers for a campaign - straight from
    Reply.io, nothing estimated or projected."""
    try:
        return outreach.get_campaign_stats(campaign_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply.io request failed: {exc}")
