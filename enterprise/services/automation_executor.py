"""Automation executor — processes events, claims and executes runs.

The executor is a long-running process with three phases:
  1. Process inbox: match NEW events to automations, create PENDING runs
  2. Claim and execute: claim PENDING runs, submit to V1 API, heartbeat
  3. Stale recovery: recover RUNNING runs with expired heartbeats
"""

import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from services.openhands_api_client import OpenHandsAPIClient
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from storage.automation import Automation, AutomationRun
from storage.automation_event import AutomationEvent

logger = logging.getLogger('saas.automation.executor')

# Environment-configurable settings
POLL_INTERVAL_SECONDS = float(os.getenv('POLL_INTERVAL_SECONDS', '30'))
HEARTBEAT_INTERVAL_SECONDS = float(os.getenv('HEARTBEAT_INTERVAL_SECONDS', '60'))
RUN_TIMEOUT_SECONDS = float(os.getenv('RUN_TIMEOUT_SECONDS', '7200'))
MAX_CONCURRENT_RUNS = int(os.getenv('MAX_CONCURRENT_RUNS', '5'))
STALE_THRESHOLD_MINUTES = 5
MAX_EVENTS_PER_BATCH = 50
MAX_RETRIES_DEFAULT = 3

# Terminal conversation statuses
TERMINAL_STATUSES = frozenset({'STOPPED', 'ERROR', 'COMPLETED', 'CANCELLED'})

# Shutdown flag — set by signal handlers
_shutdown_event: asyncio.Event | None = None

# Background task tracking for graceful shutdown
_pending_tasks: set[asyncio.Task] = set()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_shutdown_event() -> asyncio.Event:
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()
    return _shutdown_event


def should_continue() -> bool:
    return not get_shutdown_event().is_set()


def request_shutdown() -> None:
    get_shutdown_event().set()


# ---------------------------------------------------------------------------
# Phase 1: Process inbox (event matching)
# ---------------------------------------------------------------------------


async def find_matching_automations(
    session: AsyncSession, event: AutomationEvent
) -> list[Automation]:
    """Find automations that match the given event.

    Phase 1 supports cron and manual triggers only — both carry
    ``automation_id`` in the event payload.
    """
    source_type = event.source_type
    payload = event.payload
    if payload is None:
        logger.error('Event %s has None payload — possible data corruption', event.id)
        return []

    if source_type in ('cron', 'manual'):
        automation_id = payload.get('automation_id')
        if not automation_id:
            logger.warning(
                'Event %s (source=%s) missing automation_id in payload',
                event.id,
                source_type,
            )
            return []

        result = await session.execute(
            select(Automation).where(
                Automation.id == automation_id,
                Automation.enabled.is_(True),
            )
        )
        automation = result.scalar_one_or_none()
        return [automation] if automation else []

    logger.debug('Unhandled event source_type=%s for event %s', source_type, event.id)
    return []


async def process_new_events(session: AsyncSession) -> int:
    """Claim NEW events from inbox, match to automations, create runs.

    Returns the number of events processed.
    """
    result = await session.execute(
        select(AutomationEvent)
        .where(AutomationEvent.status == 'NEW')
        .order_by(AutomationEvent.created_at)
        .limit(MAX_EVENTS_PER_BATCH)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars())

    processed = 0
    for event in events:
        try:
            automations = await find_matching_automations(session, event)
            if not automations:
                event.status = 'NO_MATCH'
                event.processed_at = utc_now()
            else:
                for automation in automations:
                    run = AutomationRun(
                        id=uuid4().hex,
                        automation_id=automation.id,
                        event_id=event.id,
                        status='PENDING',
                        event_payload=event.payload,
                    )
                    session.add(run)
                event.status = 'PROCESSED'
                event.processed_at = utc_now()
            processed += 1
        except Exception as e:
            logger.exception('Error processing event %s', event.id)
            event.status = 'ERROR'
            event.error_detail = f'Failed during event matching: {type(e).__name__}: {e}'
            event.processed_at = utc_now()

    if processed:
        await session.commit()
        logger.info('Processed %d events', processed)

    return processed


# ---------------------------------------------------------------------------
# Phase 2: Claim and execute runs
# ---------------------------------------------------------------------------


async def resolve_user_api_key(session: AsyncSession, user_id: str) -> str | None:
    """Look up a user's API key from the api_keys table.

    Returns the first active key found, or None.
    """
    from storage.api_key import ApiKey

    result = await session.execute(
        select(ApiKey.key).where(ApiKey.user_id == user_id).limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def download_automation_file(file_store_key: str) -> bytes:
    """Download the automation .py file from object storage."""
    try:
        from openhands.server.shared import file_store
    except ImportError as exc:
        raise RuntimeError(
            'file_store is not available — ensure the enterprise server '
            'has been initialised before calling download_automation_file'
        ) from exc

    content = file_store.read(file_store_key)
    if isinstance(content, str):
        return content.encode('utf-8')
    return content


def is_terminal(conversation: dict) -> bool:
    """Check if a conversation has reached a terminal status."""
    status = (conversation.get('status') or '').upper()
    return status in TERMINAL_STATUSES


async def _prepare_run(
    run: AutomationRun,
    automation: Automation,
    session_factory: object,
) -> tuple[str, bytes]:
    """Resolve the user's API key and download the automation file.

    Returns:
        (api_key, automation_file) tuple ready for submission.

    Raises:
        ValueError: If no API key is found.
        RuntimeError: If file_store is unavailable.
    """
    async with session_factory() as key_session:
        api_key = await resolve_user_api_key(key_session, automation.user_id)

    if not api_key:
        raise ValueError(f'No API key found for user {automation.user_id}')

    automation_file = await download_automation_file(automation.file_store_key)
    return api_key, automation_file


async def _monitor_conversation(
    run: AutomationRun,
    conversation_id: str,
    api_client: OpenHandsAPIClient,
    api_key: str,
    session_factory: object,
) -> bool:
    """Monitor a conversation until completion or timeout.

    Returns True if completed successfully, False if shutdown requested.

    Raises:
        TimeoutError: If the run exceeds RUN_TIMEOUT_SECONDS.
    """
    start_time = utc_now()
    while should_continue():
        elapsed = (utc_now() - start_time).total_seconds()
        if elapsed > RUN_TIMEOUT_SECONDS:
            raise TimeoutError(f'Run exceeded {RUN_TIMEOUT_SECONDS}s timeout')

        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

        # Update heartbeat
        async with session_factory() as session:
            run_obj = await session.get(AutomationRun, run.id)
            if run_obj:
                run_obj.heartbeat_at = utc_now()
                await session.commit()

        # Check conversation status
        conversation = (
            await api_client.get_conversation(api_key, conversation_id) or {}
        )
        if is_terminal(conversation):
            return True

    return False  # shutdown requested


async def _submit_and_monitor(
    run: AutomationRun,
    api_key: str,
    automation_file: bytes,
    automation: Automation,
    api_client: OpenHandsAPIClient,
    session_factory: object,
) -> None:
    """Submit the automation to the V1 API and monitor until completion.

    Updates the run's conversation_id, sends heartbeats, and marks the
    final status when the conversation reaches a terminal state.
    """
    conversation = await api_client.start_conversation(
        api_key=api_key,
        automation_file=automation_file,
        title=f'Automation: {automation.name}',
        event_payload=run.event_payload,
    )

    conversation_id = conversation.get('app_conversation_id') or conversation.get(
        'conversation_id'
    )

    # Persist conversation ID
    async with session_factory() as update_session:
        run_obj = await update_session.get(AutomationRun, run.id)
        if run_obj:
            run_obj.conversation_id = conversation_id
            await update_session.commit()

    # Monitor with heartbeats
    completed = await _monitor_conversation(
        run, conversation_id, api_client, api_key, session_factory
    )

    # Update final status
    async with session_factory() as final_session:
        run_obj = await final_session.get(AutomationRun, run.id)
        if run_obj:
            if not completed:
                # Leave as RUNNING — stale recovery will handle it if needed.
                # The conversation may still be running on the API side.
                logger.info(
                    'Run %s left as RUNNING due to executor shutdown', run.id
                )
            else:
                run_obj.status = 'COMPLETED'
                run_obj.completed_at = utc_now()
                logger.info('Run %s completed successfully', run.id)
            await final_session.commit()


async def execute_run(
    run: AutomationRun,
    automation: Automation,
    api_client: OpenHandsAPIClient,
    session_factory: object,
) -> None:
    """Execute a single automation run end-to-end.

    Orchestrates preparation (API key + file download) and submission/monitoring.
    On failure, marks the run for retry or dead-letter.
    """
    try:
        api_key, automation_file = await _prepare_run(
            run, automation, session_factory
        )
        await _submit_and_monitor(
            run, api_key, automation_file, automation, api_client, session_factory
        )
    except Exception as e:
        logger.exception('Run %s failed: %s', run.id, e)
        await _mark_run_failed(run, str(e), session_factory)


async def _mark_run_failed(
    run: AutomationRun, error: str, session_factory: object
) -> None:
    """Mark a run as FAILED or return to PENDING for retry."""
    async with session_factory() as session:
        run_obj = await session.get(AutomationRun, run.id)
        if not run_obj:
            return

        run_obj.retry_count = (run_obj.retry_count or 0) + 1
        run_obj.error_detail = error

        if run_obj.retry_count >= (run_obj.max_retries or MAX_RETRIES_DEFAULT):
            run_obj.status = 'DEAD_LETTER'
            run_obj.completed_at = utc_now()
            logger.error(
                'Run %s moved to DEAD_LETTER after %d retries',
                run.id,
                run_obj.retry_count,
            )
        else:
            run_obj.status = 'PENDING'
            run_obj.claimed_by = None
            backoff_seconds = 30 * (2 ** (run_obj.retry_count - 1))
            run_obj.next_retry_at = utc_now() + timedelta(seconds=backoff_seconds)
            logger.warning(
                'Run %s returned to PENDING, retry %d/%d in %ds',
                run.id,
                run_obj.retry_count,
                run_obj.max_retries or MAX_RETRIES_DEFAULT,
                backoff_seconds,
            )

        await session.commit()


async def claim_and_execute_runs(
    session: AsyncSession,
    executor_id: str,
    api_client: OpenHandsAPIClient,
    session_factory: object,
) -> bool:
    """Claim a PENDING run and start executing it.

    Returns True if a run was claimed, False otherwise.
    """
    result = await session.execute(
        select(AutomationRun)
        .where(
            AutomationRun.status == 'PENDING',
            or_(
                AutomationRun.next_retry_at.is_(None),
                AutomationRun.next_retry_at <= utc_now(),
            ),
        )
        .order_by(AutomationRun.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run = result.scalar_one_or_none()
    if not run:
        return False

    # Claim the run
    run.status = 'RUNNING'
    run.claimed_by = executor_id
    run.claimed_at = utc_now()
    run.heartbeat_at = utc_now()
    run.started_at = utc_now()
    await session.commit()

    # Load automation for the run
    auto_result = await session.execute(
        select(Automation).where(Automation.id == run.automation_id)
    )
    automation = auto_result.scalar_one_or_none()
    if not automation:
        logger.error('Automation %s not found for run %s', run.automation_id, run.id)
        await _mark_run_failed(
            run, f'Automation {run.automation_id} not found', session_factory
        )
        return True

    # Execute in background (long-running) with task tracking
    task = asyncio.create_task(
        execute_run(run, automation, api_client, session_factory),
        name=f'execute-run-{run.id}',
    )
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)

    logger.info(
        'Claimed run %s (automation=%s) by executor %s',
        run.id,
        run.automation_id,
        executor_id,
    )
    return True


# ---------------------------------------------------------------------------
# Phase 3: Stale run recovery
# ---------------------------------------------------------------------------


async def recover_stale_runs(session: AsyncSession) -> int:
    """Mark RUNNING runs with expired heartbeats as PENDING for retry.

    Returns the number of recovered runs.
    """
    stale_threshold = utc_now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    timeout_threshold = utc_now() - timedelta(seconds=RUN_TIMEOUT_SECONDS)

    # Recover stale runs (heartbeat expired)
    result = await session.execute(
        update(AutomationRun)
        .where(
            AutomationRun.status == 'RUNNING',
            AutomationRun.heartbeat_at < stale_threshold,
            AutomationRun.heartbeat_at >= timeout_threshold,
        )
        .values(
            status='PENDING',
            claimed_by=None,
            retry_count=AutomationRun.retry_count + 1,
            next_retry_at=utc_now() + timedelta(seconds=30),
        )
        .returning(AutomationRun.id)
    )
    recovered_rows = result.fetchall()

    # Mark truly timed-out runs as DEAD_LETTER
    timeout_result = await session.execute(
        update(AutomationRun)
        .where(
            AutomationRun.status == 'RUNNING',
            AutomationRun.heartbeat_at < timeout_threshold,
        )
        .values(
            status='DEAD_LETTER',
            error_detail='Run exceeded timeout',
            completed_at=utc_now(),
        )
        .returning(AutomationRun.id)
    )
    timed_out_rows = timeout_result.fetchall()

    await session.commit()

    recovered_count = len(recovered_rows)
    timed_out_count = len(timed_out_rows)

    if recovered_count:
        logger.warning('Recovered %d stale automation runs', recovered_count)
    if timed_out_count:
        logger.warning(
            'Marked %d automation runs as DEAD_LETTER (timeout)', timed_out_count
        )

    return recovered_count + timed_out_count


# ---------------------------------------------------------------------------
# Main executor loop
# ---------------------------------------------------------------------------


async def executor_main(session_factory: object | None = None) -> None:
    """Main executor loop.

    Args:
        session_factory: Async context manager that yields AsyncSession instances.
            If None, uses the default ``a_session_maker`` from database module.
    """
    if session_factory is None:
        from storage.database import a_session_maker

        session_factory = a_session_maker

    executor_id = f'executor-{socket.gethostname()}-{os.getpid()}'
    api_url = os.getenv('OPENHANDS_API_URL', 'http://openhands-service:3000')
    api_client = OpenHandsAPIClient(base_url=api_url)

    logger.info(
        'Automation executor %s starting (api_url=%s, poll=%ss, heartbeat=%ss)',
        executor_id,
        api_url,
        POLL_INTERVAL_SECONDS,
        HEARTBEAT_INTERVAL_SECONDS,
    )

    try:
        while should_continue():
            try:
                async with session_factory() as session:
                    await process_new_events(session)

                async with session_factory() as session:
                    await claim_and_execute_runs(
                        session, executor_id, api_client, session_factory
                    )

                async with session_factory() as session:
                    await recover_stale_runs(session)

            except Exception:
                logger.exception('Error in executor main loop iteration')

            # Wait for next poll interval (or early wakeup on shutdown)
            try:
                await asyncio.wait_for(
                    get_shutdown_event().wait(),
                    timeout=POLL_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass  # Normal — poll interval elapsed

    finally:
        if _pending_tasks:
            logger.info(
                'Waiting for %d running tasks to complete...', len(_pending_tasks)
            )
            await asyncio.gather(*_pending_tasks, return_exceptions=True)
        await api_client.close()
        logger.info('Automation executor %s shut down', executor_id)
