"""
First-admin bootstrap.

Public signup can never create an admin, so the owner needs one safe way to
get the first admin account. If ADMIN_BOOTSTRAP_EMAIL and
ADMIN_BOOTSTRAP_PASSWORD are set and no admin exists yet, one is created at
startup. Once an admin exists this does nothing, so the password variable can
(and should) be deleted from the host afterward.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


def ensure_admin(db: Session) -> Optional[str]:
    """Returns a short status string, or None if nothing was configured."""
    settings = get_settings()
    email = settings.admin_bootstrap_email.strip()
    password = settings.admin_bootstrap_password
    if not email or not password:
        return None

    if db.query(User).filter(User.role == UserRole.ADMIN).first():
        return "admin already exists; bootstrap skipped (you can delete ADMIN_BOOTSTRAP_PASSWORD)"

    if len(password) < 12:
        return "bootstrap skipped: ADMIN_BOOTSTRAP_PASSWORD must be at least 12 characters"

    if db.query(User).filter(User.email == email).first():
        return "bootstrap skipped: that email is already registered as a non-admin user"

    db.add(
        User(
            email=email,
            hashed_password=hash_password(password),
            full_name="Platform Administrator",
            role=UserRole.ADMIN,
        )
    )
    db.commit()
    return "admin account created; delete ADMIN_BOOTSTRAP_PASSWORD from the host now"
