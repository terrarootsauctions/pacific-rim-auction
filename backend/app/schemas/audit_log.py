from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: str
    actor_user_id: str
    actor_role: Optional[str]
    entity_type: str
    entity_id: str
    action: str
    before_state: Optional[str]
    after_state: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
