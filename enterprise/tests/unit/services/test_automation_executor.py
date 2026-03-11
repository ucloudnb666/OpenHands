"""Tests for the automation executor.

Uses real SQLite database operations for event processing, run claiming,
and stale run recovery. HTTP calls to the V1 API are mocked.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from services.automation_executor import (
    _mark_run_failed,
    claim_and_execute_runs,
    find_matching_automations,
    is_terminal,
    process_new_events,
    recover_stale_runs,
    utc_now,
)
from sqlalchemy import select
from storage.automation import Automation, AutomationRun
from storage.automation_event import AutomationEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_automation(
    automation_id: str = 'auto-1',
    user_id: str = 'user-1',
    enabled: bool = True,
    trigger_type: str = 'cron',
    name: str = 'Test Automation',
) -> Automation:
    return Automation(
        id=automation_id,
        user_id=user_id,
        org_id='org-1',
        name=name,
        enabled=enabled,
        config={'triggers': {'cron': {'schedule': '0 9 * * 5'}}},
        trigger_type=trigger_type,
        file_store_key=f'automations/{automation_id}/script.py',
    )


def make_event(
    source_type: str = 'cron',
    payload: dict | None = None,
    status: str = 'NEW',
    dedup_key: str | None = None,
) -> AutomationEvent:
    return AutomationEvent(
        source_type=source_type,
        payload=payload or {'automation_id': 'auto-1'},
        dedup_key=dedup_key or f'dedup-{uuid4().hex[:8]}',
        status=status,
        created_at=utc_now(),
    )


def make_run(
    run_id: str | None = None,
    automation_id: str = 'auto-1',
    status: str = 'PENDING',
    claimed_by: str | None = None,
    heartbeat_at: datetime | None = None,
    retry_count: int = 0,
    max_retries: int = 3,
    next_retry_at: datetime | None = None,
) -> AutomationRun:
    return AutomationRun(
        id=run_id or uuid4().hex,
        automation_id=automation_id,
        status=status,
        claimed_by=claimed_by,
        heartbeat_at=heartbeat_at,
        retry_count=retry_count,
        max_retries=max_retries,
        next_retry_at=next_retry_at,
        event_payload={'automation_id': automation_id},
        created_at=utc_now(),
    )


# ---------------------------------------------------------------------------
# find_matching_automations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_matching_automations_cron_event(async_session):
    """Cron events match by automation_id in payload."""
    automation = make_automation()
    async_session.add(automation)
    await async_session.commit()

    event = make_event(source_type='cron', payload={'automation_id': 'auto-1'})
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert len(result) == 1
    assert result[0].id == 'auto-1'


@pytest.mark.asyncio
async def test_find_matching_automations_manual_event(async_session):
    """Manual events also match by automation_id in payload."""
    automation = make_automation()
    async_session.add(automation)
    await async_session.commit()

    event = make_event(source_type='manual', payload={'automation_id': 'auto-1'})
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert len(result) == 1
    assert result[0].id == 'auto-1'


@pytest.mark.asyncio
async def test_find_matching_automations_disabled_automation(async_session):
    """Disabled automations are not matched."""
    automation = make_automation(enabled=False)
    async_session.add(automation)
    await async_session.commit()

    event = make_event(payload={'automation_id': 'auto-1'})
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_find_matching_automations_missing_automation_id(async_session):
    """Events without automation_id in payload return empty list."""
    event = make_event(payload={'something_else': 'value'})
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_find_matching_automations_nonexistent_automation(async_session):
    """Events referencing a non-existent automation return empty list."""
    event = make_event(payload={'automation_id': 'nonexistent'})
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_find_matching_automations_unknown_source_type(async_session):
    """Unknown source types return empty list."""
    event = make_event(source_type='unknown', payload={'automation_id': 'auto-1'})
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert len(result) == 0


# ---------------------------------------------------------------------------
# process_new_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_new_events_creates_runs(async_session):
    """Processing NEW events creates PENDING runs and marks events PROCESSED."""
    automation = make_automation()
    event = make_event(payload={'automation_id': 'auto-1'})
    async_session.add_all([automation, event])
    await async_session.commit()

    count = await process_new_events(async_session)

    assert count == 1

    # Event should be PROCESSED
    await async_session.refresh(event)
    assert event.status == 'PROCESSED'
    assert event.processed_at is not None

    # A run should have been created
    runs = (await async_session.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].automation_id == 'auto-1'
    assert runs[0].status == 'PENDING'
    assert runs[0].event_payload == {'automation_id': 'auto-1'}


@pytest.mark.asyncio
async def test_process_new_events_no_match(async_session):
    """Events with no matching automation are marked NO_MATCH."""
    event = make_event(payload={'automation_id': 'nonexistent'})
    async_session.add(event)
    await async_session.commit()

    count = await process_new_events(async_session)

    assert count == 1

    await async_session.refresh(event)
    assert event.status == 'NO_MATCH'
    assert event.processed_at is not None

    # No runs created
    runs = (await async_session.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 0


@pytest.mark.asyncio
async def test_process_new_events_skips_processed(async_session):
    """Already processed events are not re-processed."""
    event = make_event(status='PROCESSED')
    async_session.add(event)
    await async_session.commit()

    count = await process_new_events(async_session)

    assert count == 0


@pytest.mark.asyncio
async def test_process_new_events_multiple_events(async_session):
    """Multiple NEW events are processed in one batch."""
    auto1 = make_automation(automation_id='auto-1')
    auto2 = make_automation(automation_id='auto-2', name='Auto 2')
    event1 = make_event(payload={'automation_id': 'auto-1'}, dedup_key='dedup-1')
    event2 = make_event(payload={'automation_id': 'auto-2'}, dedup_key='dedup-2')
    event3 = make_event(payload={'automation_id': 'nonexistent'}, dedup_key='dedup-3')
    async_session.add_all([auto1, auto2, event1, event2, event3])
    await async_session.commit()

    count = await process_new_events(async_session)

    assert count == 3

    # Two runs created (for auto-1 and auto-2), none for nonexistent
    runs = (await async_session.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 2

    await async_session.refresh(event1)
    await async_session.refresh(event2)
    await async_session.refresh(event3)
    assert event1.status == 'PROCESSED'
    assert event2.status == 'PROCESSED'
    assert event3.status == 'NO_MATCH'


# ---------------------------------------------------------------------------
# claim_and_execute_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_and_execute_runs_claims_pending(
    async_session, async_session_factory
):
    """Claims a PENDING run and transitions to RUNNING."""
    automation = make_automation()
    run = make_run(run_id='run-1')
    async_session.add_all([automation, run])
    await async_session.commit()

    api_client = AsyncMock()

    with patch('services.automation_executor.execute_run', new_callable=AsyncMock):
        claimed = await claim_and_execute_runs(
            async_session, 'executor-test-1', api_client, async_session_factory
        )

    assert claimed is True

    await async_session.refresh(run)
    assert run.status == 'RUNNING'
    assert run.claimed_by == 'executor-test-1'
    assert run.claimed_at is not None
    assert run.heartbeat_at is not None
    assert run.started_at is not None


@pytest.mark.asyncio
async def test_claim_and_execute_runs_no_pending(async_session, async_session_factory):
    """Returns False when no PENDING runs exist."""
    api_client = AsyncMock()

    claimed = await claim_and_execute_runs(
        async_session, 'executor-test-1', api_client, async_session_factory
    )

    assert claimed is False


@pytest.mark.asyncio
async def test_claim_and_execute_runs_respects_next_retry_at(
    async_session, async_session_factory
):
    """Runs with future next_retry_at are not claimed."""
    automation = make_automation()
    run = make_run(
        run_id='run-retry',
        next_retry_at=utc_now() + timedelta(hours=1),
    )
    async_session.add_all([automation, run])
    await async_session.commit()

    api_client = AsyncMock()

    claimed = await claim_and_execute_runs(
        async_session, 'executor-test-1', api_client, async_session_factory
    )

    assert claimed is False


@pytest.mark.asyncio
async def test_claim_and_execute_runs_past_retry_at(
    async_session, async_session_factory
):
    """Runs with past next_retry_at are claimable."""
    automation = make_automation()
    run = make_run(
        run_id='run-retry-past',
        next_retry_at=utc_now() - timedelta(minutes=5),
    )
    async_session.add_all([automation, run])
    await async_session.commit()

    api_client = AsyncMock()

    with patch('services.automation_executor.execute_run', new_callable=AsyncMock):
        claimed = await claim_and_execute_runs(
            async_session, 'executor-test-1', api_client, async_session_factory
        )

    assert claimed is True


@pytest.mark.asyncio
async def test_claim_skips_running_runs(async_session, async_session_factory):
    """RUNNING runs are not claimed."""
    automation = make_automation()
    run = make_run(run_id='run-running', status='RUNNING', claimed_by='other-executor')
    async_session.add_all([automation, run])
    await async_session.commit()

    api_client = AsyncMock()

    claimed = await claim_and_execute_runs(
        async_session, 'executor-test-1', api_client, async_session_factory
    )

    assert claimed is False


# ---------------------------------------------------------------------------
# recover_stale_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_stale_runs_recovers_stale(async_session):
    """RUNNING runs with expired heartbeats are recovered to PENDING."""
    automation = make_automation()
    stale_run = make_run(
        run_id='stale-1',
        status='RUNNING',
        claimed_by='crashed-executor',
        heartbeat_at=utc_now() - timedelta(minutes=10),
        retry_count=0,
    )
    async_session.add_all([automation, stale_run])
    await async_session.commit()

    count = await recover_stale_runs(async_session)

    assert count >= 1

    await async_session.refresh(stale_run)
    assert stale_run.status == 'PENDING'
    assert stale_run.claimed_by is None
    assert stale_run.retry_count == 1
    assert stale_run.next_retry_at is not None


@pytest.mark.asyncio
async def test_recover_stale_runs_ignores_fresh(async_session):
    """RUNNING runs with recent heartbeats are not recovered."""
    automation = make_automation()
    fresh_run = make_run(
        run_id='fresh-1',
        status='RUNNING',
        claimed_by='active-executor',
        heartbeat_at=utc_now() - timedelta(seconds=30),
    )
    async_session.add_all([automation, fresh_run])
    await async_session.commit()

    count = await recover_stale_runs(async_session)

    assert count == 0

    await async_session.refresh(fresh_run)
    assert fresh_run.status == 'RUNNING'
    assert fresh_run.claimed_by == 'active-executor'


@pytest.mark.asyncio
async def test_recover_stale_runs_ignores_pending(async_session):
    """PENDING runs are not affected by recovery."""
    automation = make_automation()
    pending_run = make_run(run_id='pending-1', status='PENDING')
    async_session.add_all([automation, pending_run])
    await async_session.commit()

    count = await recover_stale_runs(async_session)

    assert count == 0

    await async_session.refresh(pending_run)
    assert pending_run.status == 'PENDING'


@pytest.mark.asyncio
async def test_recover_stale_runs_increments_retry_count(async_session):
    """Recovery increments the retry_count."""
    automation = make_automation()
    stale_run = make_run(
        run_id='stale-retry',
        status='RUNNING',
        claimed_by='old-executor',
        heartbeat_at=utc_now() - timedelta(minutes=10),
        retry_count=2,
    )
    async_session.add_all([automation, stale_run])
    await async_session.commit()

    await recover_stale_runs(async_session)

    await async_session.refresh(stale_run)
    assert stale_run.retry_count == 3


# ---------------------------------------------------------------------------
# _mark_run_failed (error handling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_run_failed_retries(async_session_factory):
    """Failed runs with retries left return to PENDING."""
    async with async_session_factory() as session:
        automation = make_automation()
        run = make_run(run_id='fail-retry', retry_count=0, max_retries=3)
        session.add_all([automation, run])
        await session.commit()

    async with async_session_factory() as session:
        run_obj = await session.get(AutomationRun, 'fail-retry')
        await _mark_run_failed(run_obj, 'API error', async_session_factory)

    async with async_session_factory() as session:
        run_obj = await session.get(AutomationRun, 'fail-retry')
        assert run_obj.status == 'PENDING'
        assert run_obj.retry_count == 1
        assert run_obj.error_detail == 'API error'
        assert run_obj.next_retry_at is not None
        assert run_obj.claimed_by is None


@pytest.mark.asyncio
async def test_mark_run_failed_dead_letter(async_session_factory):
    """Failed runs that exceed max_retries go to DEAD_LETTER."""
    async with async_session_factory() as session:
        automation = make_automation()
        run = make_run(run_id='fail-dead', retry_count=2, max_retries=3)
        session.add_all([automation, run])
        await session.commit()

    async with async_session_factory() as session:
        run_obj = await session.get(AutomationRun, 'fail-dead')
        await _mark_run_failed(run_obj, 'Final failure', async_session_factory)

    async with async_session_factory() as session:
        run_obj = await session.get(AutomationRun, 'fail-dead')
        assert run_obj.status == 'DEAD_LETTER'
        assert run_obj.retry_count == 3
        assert run_obj.error_detail == 'Final failure'
        assert run_obj.completed_at is not None


# ---------------------------------------------------------------------------
# is_terminal
# ---------------------------------------------------------------------------


def test_is_terminal_stopped():
    assert is_terminal({'status': 'STOPPED'}) is True


def test_is_terminal_error():
    assert is_terminal({'status': 'ERROR'}) is True


def test_is_terminal_completed():
    assert is_terminal({'status': 'COMPLETED'}) is True


def test_is_terminal_cancelled():
    assert is_terminal({'status': 'CANCELLED'}) is True


def test_is_terminal_running():
    assert is_terminal({'status': 'RUNNING'}) is False


def test_is_terminal_empty():
    assert is_terminal({}) is False


def test_is_terminal_case_insensitive():
    assert is_terminal({'status': 'stopped'}) is True
    assert is_terminal({'status': 'Completed'}) is True


# ---------------------------------------------------------------------------
# find_matching_automations — None payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_matching_automations_none_payload(async_session):
    """Events with None payload return empty list (data corruption guard)."""
    event = make_event(source_type='cron')
    event.payload = None
    async_session.add(event)
    await async_session.commit()

    result = await find_matching_automations(async_session, event)

    assert result == []


# ---------------------------------------------------------------------------
# Integration: event → run creation → claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_event_to_run_to_claim(
    async_session_factory,
):
    """Full flow: create event + automation → process_new_events → claim_and_execute_runs.

    Uses a real SQLite database; only the external API client is mocked.
    """
    # 1. Seed an automation and a NEW event
    async with async_session_factory() as session:
        automation = make_automation(automation_id='integ-auto')
        event = make_event(
            source_type='cron',
            payload={'automation_id': 'integ-auto'},
            dedup_key='integ-dedup',
        )
        session.add_all([automation, event])
        await session.commit()
        event_id = event.id

    # 2. Process inbox — should match and create a PENDING run
    async with async_session_factory() as session:
        processed = await process_new_events(session)

    assert processed == 1

    # Verify event is PROCESSED and run was created
    async with async_session_factory() as session:
        evt = await session.get(AutomationEvent, event_id)
        assert evt.status == 'PROCESSED'

        runs = (await session.execute(select(AutomationRun))).scalars().all()
        assert len(runs) == 1
        run = runs[0]
        assert run.automation_id == 'integ-auto'
        assert run.status == 'PENDING'
        assert run.event_payload == {'automation_id': 'integ-auto'}

    # 3. Claim the run — mock execute_run to avoid real API calls
    api_client = AsyncMock()

    with patch('services.automation_executor.execute_run', new_callable=AsyncMock):
        async with async_session_factory() as session:
            claimed = await claim_and_execute_runs(
                session, 'executor-integ', api_client, async_session_factory
            )

    assert claimed is True

    # 4. Verify the run moved to RUNNING with correct executor
    async with async_session_factory() as session:
        runs = (await session.execute(select(AutomationRun))).scalars().all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == 'RUNNING'
        assert run.claimed_by == 'executor-integ'
        assert run.started_at is not None
        assert run.heartbeat_at is not None
