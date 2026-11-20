from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    country: Optional[str] = None
    role: UserRole = UserRole.BUYER


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str]
    role: UserRole
    country: Optional[str]
    is_active: bool
    kyc_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
