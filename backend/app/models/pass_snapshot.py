"""
One row per saved pass: where every open asset stood at that moment.
Only ever inserted. It is bookkeeping for the pass report and changes no
asset, listing, ledger entry or payment.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Text

from app.core.database import Base


class PassSnapshot(Base):
    __tablename__ = "pass_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taken_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    data_json = Column(Text, nullable=False)
