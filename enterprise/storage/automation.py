"""SQLAlchemy models for automations.

NOTE: This is a stub for Task 2 (CRUD API) development.
Task 1 (Data Foundation) will provide the full implementation.
"""

from sqlalchemy import JSON, Boolean, Column, DateTime, String
from sqlalchemy.sql import func
from storage.base import Base


class Automation(Base):  # type: ignore
    __tablename__ = 'automations'

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    org_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=False)
    trigger_type = Column(String, nullable=False)
    file_store_key = Column(String, nullable=False)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AutomationRun(Base):  # type: ignore
    __tablename__ = 'automation_runs'

    id = Column(String, primary_key=True)
    automation_id = Column(String, nullable=False, index=True)
    conversation_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default='PENDING')
    error_detail = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
