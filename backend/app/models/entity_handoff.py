"""
EntityHandoff - records an asset passing from one platform entity to
another (for example a physical property from Pacific Rim Auctions to
TerraRoots). A NEW table: create_all() adds new tables but never columns.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class EntityHandoff(Base):
    __tablename__ = "entity_handoffs"

    id = Column(String, primary_key=True, default=gen_uuid)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=False, index=True)
    from_entity = Column(String, nullable=False)
    to_entity = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    recorded_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
