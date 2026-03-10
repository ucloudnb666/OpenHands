"""FastAPI router for automation CRUD API (Phase 1: simple mode only)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from services.automation_config import extract_config, validate_config
from services.automation_event_publisher import publish_automation_event
from services.automation_file_generator import generate_automation_file
from sqlalchemy import delete, func, select
from storage.automation import Automation, AutomationRun
from storage.database import a_session_maker

from openhands.core.logger import openhands_logger as logger
from openhands.server.shared import file_store
from openhands.server.user_auth import get_user_id

from .automation_models import (
    AutomationResponse,
    AutomationRunResponse,
    CreateAutomationRequest,
    PaginatedAutomationsResponse,
    PaginatedRunsResponse,
    UpdateAutomationRequest,
)

automation_router = APIRouter(
    prefix='/api/v1/automations',
    tags=['automations'],
)

FILE_STORE_PREFIX = 'automations'


def _file_store_key(automation_id: str) -> str:
    return f'{FILE_STORE_PREFIX}/{automation_id}/automation.py'


def _automation_to_response(automation: Automation) -> AutomationResponse:
    return AutomationResponse(
        id=automation.id,
        name=automation.name,
        enabled=automation.enabled,
        trigger_type=automation.trigger_type,
        config=automation.config or {},
        file_url=None,
        last_triggered_at=(
            automation.last_triggered_at.isoformat()
            if automation.last_triggered_at
            else None
        ),
        created_at=automation.created_at.isoformat(),
        updated_at=automation.updated_at.isoformat(),
    )


def _run_to_response(run: AutomationRun) -> AutomationRunResponse:
    return AutomationRunResponse(
        id=run.id,
        automation_id=run.automation_id,
        conversation_id=run.conversation_id,
        status=run.status,
        error_detail=run.error_detail,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        created_at=run.created_at.isoformat(),
    )


def _generate_and_validate_file(
    name: str,
    schedule: str,
    timezone: str,
    prompt: str,
    repository: str | None = None,
    branch: str | None = None,
) -> tuple[str, dict]:
    """Generate automation file, extract and validate config.

    Returns (file_content, config_dict).
    Raises HTTPException on validation failure.
    """
    file_content = generate_automation_file(
        name=name,
        schedule=schedule,
        timezone=timezone,
        prompt=prompt,
        repository=repository,
        branch=branch,
    )
    config = extract_config(file_content)
    try:
        validate_config(config)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f'Invalid automation config: {e}',
        )
    return file_content, config


@automation_router.post('', status_code=status.HTTP_201_CREATED)
async def create_automation(
    request: CreateAutomationRequest,
    user_id: str = Depends(get_user_id),
) -> AutomationResponse:
    """Create an automation from simple mode input (Phase 1).

    Generates a .py file, uploads to object store, stores metadata in DB.
    """
    file_content, config = _generate_and_validate_file(
        name=request.name,
        schedule=request.schedule,
        timezone=request.timezone,
        prompt=request.prompt,
        repository=request.repository,
        branch=request.branch,
    )

    automation_id = uuid.uuid4().hex
    key = _file_store_key(automation_id)

    try:
        file_store.write(key, file_content)
    except Exception:
        logger.exception('Failed to upload automation file to object store')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to store automation file',
        )

    automation = Automation(
        id=automation_id,
        user_id=user_id,
        name=request.name,
        enabled=True,
        config=config,
        trigger_type='cron',
        file_store_key=key,
    )

    async with a_session_maker() as session:
        session.add(automation)
        await session.commit()
        await session.refresh(automation)

    logger.info(
        'Created automation',
        extra={'automation_id': automation_id, 'user_id': user_id},
    )
    return _automation_to_response(automation)


@automation_router.get('/search')
async def search_automations(
    user_id: str = Depends(get_user_id),
    page_id: Annotated[
        str | None,
        Query(title='Cursor for pagination (automation ID)'),
    ] = None,
    limit: Annotated[
        int,
        Query(title='Max results per page', gt=0, le=100),
    ] = 20,
) -> PaginatedAutomationsResponse:
    """List automations for the current user, paginated."""
    async with a_session_maker() as session:
        base_filter = select(Automation).where(Automation.user_id == user_id)

        # Total count
        count_q = select(func.count()).select_from(base_filter.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        # Paginated query ordered by created_at desc
        query = base_filter.order_by(Automation.created_at.desc())
        if page_id:
            cursor_row = (
                await session.execute(
                    select(Automation.created_at).where(Automation.id == page_id)
                )
            ).scalar()
            if cursor_row is not None:
                query = query.where(Automation.created_at < cursor_row)

        query = query.limit(limit + 1)
        result = await session.execute(query)
        rows = list(result.scalars().all())

    next_page_id: str | None = None
    if len(rows) > limit:
        next_page_id = rows[limit - 1].id
        rows = rows[:limit]

    return PaginatedAutomationsResponse(
        items=[_automation_to_response(a) for a in rows],
        total=total,
        next_page_id=next_page_id,
    )


@automation_router.get('/{automation_id}')
async def get_automation(
    automation_id: str,
    user_id: str = Depends(get_user_id),
) -> AutomationResponse:
    """Get a single automation by ID."""
    async with a_session_maker() as session:
        result = await session.execute(
            select(Automation).where(
                Automation.id == automation_id,
                Automation.user_id == user_id,
            )
        )
        automation = result.scalars().first()

    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Automation not found',
        )
    return _automation_to_response(automation)


@automation_router.patch('/{automation_id}')
async def update_automation(
    automation_id: str,
    request: UpdateAutomationRequest,
    user_id: str = Depends(get_user_id),
) -> AutomationResponse:
    """Update an automation. Re-generates file if prompt/schedule/timezone changed."""
    async with a_session_maker() as session:
        result = await session.execute(
            select(Automation).where(
                Automation.id == automation_id,
                Automation.user_id == user_id,
            )
        )
        automation = result.scalars().first()
        if not automation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Automation not found',
            )

        # Determine if we need to regenerate the file
        current_config = automation.config or {}
        current_triggers = current_config.get('triggers', {}).get('cron', {})
        current_schedule = current_triggers.get('schedule', '')
        current_timezone = current_triggers.get('timezone', 'UTC')

        new_name = request.name if request.name is not None else automation.name
        new_schedule = (
            request.schedule if request.schedule is not None else current_schedule
        )
        new_timezone = (
            request.timezone if request.timezone is not None else current_timezone
        )

        needs_regen = (
            request.prompt is not None
            or request.schedule is not None
            or request.timezone is not None
            or request.name is not None
        )

        if needs_regen:
            # We need the prompt — if not supplied in this request, read from file
            if request.prompt is not None:
                prompt = request.prompt
            else:
                try:
                    file_content = file_store.read(automation.file_store_key)
                    # Extract prompt from the stored file by looking for send_message call
                    prompt = _extract_prompt_from_file(file_content)
                except Exception:
                    logger.warning(
                        'Could not read existing automation file for prompt extraction',
                        extra={'automation_id': automation_id},
                    )
                    prompt = ''

            file_content, config = _generate_and_validate_file(
                name=new_name,
                schedule=new_schedule,
                timezone=new_timezone,
                prompt=prompt,
                repository=request.repository,
                branch=request.branch,
            )
            try:
                file_store.write(automation.file_store_key, file_content)
            except Exception:
                logger.exception('Failed to upload updated automation file')
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to store updated automation file',
                )
            automation.config = config
            automation.name = new_name

        elif request.name is not None:
            automation.name = request.name

        if request.enabled is not None:
            automation.enabled = request.enabled

        await session.commit()
        await session.refresh(automation)

    return _automation_to_response(automation)


def _extract_prompt_from_file(file_content: str) -> str:
    """Best-effort extraction of the prompt from a generated automation file.

    Looks for `conversation.send_message(...)` in the file.
    """
    import ast

    try:
        tree = ast.parse(file_content)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == 'send_message'
                and node.value.args
            ):
                arg = node.value.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return arg.value
                if isinstance(arg, ast.JoinedStr):
                    # f-string — return a reconstructed version
                    return ast.unparse(arg)
    except Exception:
        pass
    return ''


@automation_router.delete('/{automation_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: str,
    user_id: str = Depends(get_user_id),
) -> None:
    """Delete an automation and all its runs."""
    async with a_session_maker() as session:
        result = await session.execute(
            select(Automation).where(
                Automation.id == automation_id,
                Automation.user_id == user_id,
            )
        )
        automation = result.scalars().first()
        if not automation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Automation not found',
            )

        # Delete runs first
        await session.execute(
            delete(AutomationRun).where(AutomationRun.automation_id == automation_id)
        )
        await session.delete(automation)
        await session.commit()

    # Best-effort cleanup of file store
    try:
        file_store.delete(automation.file_store_key)
    except Exception:
        logger.warning(
            'Failed to delete automation file from object store',
            extra={'automation_id': automation_id},
        )


@automation_router.post('/{automation_id}/run', status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_run(
    automation_id: str,
    user_id: str = Depends(get_user_id),
) -> dict:
    """Manually trigger an automation run."""
    async with a_session_maker() as session:
        result = await session.execute(
            select(Automation).where(
                Automation.id == automation_id,
                Automation.user_id == user_id,
            )
        )
        automation = result.scalars().first()
        if not automation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Automation not found',
            )

        dedup_key = f'manual-{automation_id}-{uuid.uuid4().hex}'
        await publish_automation_event(
            session=session,
            source_type='manual',
            payload={'automation_id': automation_id},
            dedup_key=dedup_key,
        )
        await session.commit()

    return {'status': 'accepted', 'dedup_key': dedup_key}


@automation_router.get('/{automation_id}/runs')
async def list_automation_runs(
    automation_id: str,
    user_id: str = Depends(get_user_id),
    page_id: Annotated[
        str | None,
        Query(title='Cursor for pagination (run ID)'),
    ] = None,
    limit: Annotated[
        int,
        Query(title='Max results per page', gt=0, le=100),
    ] = 20,
) -> PaginatedRunsResponse:
    """List runs for an automation, paginated."""
    # Verify ownership
    async with a_session_maker() as session:
        ownership = await session.execute(
            select(Automation.id).where(
                Automation.id == automation_id,
                Automation.user_id == user_id,
            )
        )
        if not ownership.scalar():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Automation not found',
            )

        base_filter = select(AutomationRun).where(
            AutomationRun.automation_id == automation_id
        )

        count_q = select(func.count()).select_from(base_filter.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        query = base_filter.order_by(AutomationRun.created_at.desc())
        if page_id:
            cursor_row = (
                await session.execute(
                    select(AutomationRun.created_at).where(AutomationRun.id == page_id)
                )
            ).scalar()
            if cursor_row is not None:
                query = query.where(AutomationRun.created_at < cursor_row)

        query = query.limit(limit + 1)
        result = await session.execute(query)
        rows = list(result.scalars().all())

    next_page_id: str | None = None
    if len(rows) > limit:
        next_page_id = rows[limit - 1].id
        rows = rows[:limit]

    return PaginatedRunsResponse(
        items=[_run_to_response(r) for r in rows],
        total=total,
        next_page_id=next_page_id,
    )


@automation_router.get('/{automation_id}/runs/{run_id}')
async def get_automation_run(
    automation_id: str,
    run_id: str,
    user_id: str = Depends(get_user_id),
) -> AutomationRunResponse:
    """Get a single run detail."""
    async with a_session_maker() as session:
        # Verify ownership of the automation
        ownership = await session.execute(
            select(Automation.id).where(
                Automation.id == automation_id,
                Automation.user_id == user_id,
            )
        )
        if not ownership.scalar():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Automation not found',
            )

        result = await session.execute(
            select(AutomationRun).where(
                AutomationRun.id == run_id,
                AutomationRun.automation_id == automation_id,
            )
        )
        run = result.scalars().first()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Run not found',
        )
    return _run_to_response(run)
