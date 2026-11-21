"""Tunable algorithm parameters. Only parameters approved in
evolution_rules.PARAMETERS ever live here, and every change is also written
to the Memory Lock as an ALGORITHM_CHANGE event."""
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from app.core.database import Base


class AlgorithmParameter(Base):
    __tablename__ = "algorithm_parameters"

    name = Column(String, primary_key=True)
    value = Column(BigInteger, nullable=False)
    previous_value = Column(BigInteger, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
