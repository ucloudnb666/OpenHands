"""Automation event publisher.

NOTE: This is a stub for Task 2 (CRUD API) development.
Task 1 (Data Foundation) will provide the full implementation.
"""

from typing import Any

from storage.automation_event import AutomationEvent


async def publish_automation_event(
    session: Any,
    source_type: str,
    payload: dict,
    dedup_key: str,
) -> AutomationEvent:
    """Insert a new automation event into the automation_events table."""
    event = AutomationEvent(
        source_type=source_type,
        payload=payload,
        dedup_key=dedup_key,
        status='NEW',
    )
    session.add(event)
    return event
