"""SQLAlchemy model for automation events.

NOTE: This is a stub for Task 2 (CRUD API) development.
Task 1 (Data Foundation) will provide the full implementation.
"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, String
from sqlalchemy.sql import func
from storage.base import Base


class AutomationEvent(Base):  # type: ignore
    __tablename__ = 'automation_events'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    metadata_ = Column('metadata', JSON, nullable=True)
    dedup_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default='NEW')
    error_detail = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)
