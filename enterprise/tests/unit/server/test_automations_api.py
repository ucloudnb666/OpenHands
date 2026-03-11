"""Unit tests for automation CRUD API routes."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from server.routes.automations import automation_router

from openhands.server.user_auth import get_user_id

TEST_USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())


def _make_automation(
    automation_id: str | None = None,
    user_id: str = TEST_USER_ID,
    name: str = 'Test Automation',
    enabled: bool = True,
    trigger_type: str = 'cron',
    schedule: str = '0 9 * * 5',
    timezone: str = 'UTC',
    file_store_key: str | None = None,
):
    auto_id = automation_id or uuid.uuid4().hex
    mock = MagicMock()
    mock.id = auto_id
    mock.user_id = user_id
    mock.name = name
    mock.enabled = enabled
    mock.trigger_type = trigger_type
    mock.config = {
        'name': name,
        'triggers': {'cron': {'schedule': schedule, 'timezone': timezone}},
    }
    mock.file_store_key = file_store_key or f'automations/{auto_id}/automation.py'
    mock.last_triggered_at = None
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return mock


def _make_run(
    run_id: str | None = None,
    automation_id: str = 'auto-1',
    conversation_id: str | None = None,
    run_status: str = 'PENDING',
):
    rid = run_id or uuid.uuid4().hex
    mock = MagicMock()
    mock.id = rid
    mock.automation_id = automation_id
    mock.conversation_id = conversation_id
    mock.status = run_status
    mock.error_detail = None
    mock.started_at = None
    mock.completed_at = None
    mock.created_at = datetime(2026, 1, 2, tzinfo=UTC)
    return mock


# --- Helpers to mock async DB sessions ---


def _mock_session_with_results(results_by_call):
    """Create a mock async session that returns preconfigured results.

    results_by_call: list of values; each session.execute() returns
    the next value wrapped in a mock result.
    """
    call_index = [0]

    session = AsyncMock()

    async def _execute(stmt):
        idx = call_index[0]
        call_index[0] += 1
        val = results_by_call[idx] if idx < len(results_by_call) else None
        result_mock = MagicMock()
        if isinstance(val, list):
            result_mock.scalars.return_value.all.return_value = val
            result_mock.scalars.return_value.first.return_value = (
                val[0] if val else None
            )
            result_mock.scalar.return_value = len(val)
        elif val is None:
            result_mock.scalars.return_value.first.return_value = None
            result_mock.scalars.return_value.all.return_value = []
            result_mock.scalar.return_value = None
        else:
            result_mock.scalars.return_value.first.return_value = val
            result_mock.scalar.return_value = val
        return result_mock

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    return session


@asynccontextmanager
async def _session_ctx(session):
    yield session


# --- Fixtures ---


@pytest.fixture
def mock_app():
    """Create a test FastAPI app with automation routes and mocked auth."""
    app = FastAPI()
    app.include_router(automation_router)

    def mock_get_user_id():
        return TEST_USER_ID

    app.dependency_overrides[get_user_id] = mock_get_user_id
    return app


@pytest.fixture
def client(mock_app):
    return TestClient(mock_app)


# --- Test: POST /api/v1/automations ---


class TestCreateAutomation:
    def test_create_success(self, client):
        """POST with valid input → 201 with AutomationResponse."""
        mock_session = _mock_session_with_results([])

        async def fake_refresh(obj):
            obj.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            obj.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
            obj.last_triggered_at = None

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        with (
            patch(
                'server.routes.automations.generate_automation_file',
                return_value='__config__ = {"name": "Test", "triggers": {"cron": {"schedule": "0 9 * * 5"}}}',
            ),
            patch(
                'server.routes.automations.extract_config',
                return_value={
                    'name': 'Test',
                    'triggers': {'cron': {'schedule': '0 9 * * 5'}},
                },
            ),
            patch('server.routes.automations.validate_config'),
            patch('server.routes.automations.file_store') as mock_fs,
            patch(
                'server.routes.automations.a_session_maker',
                return_value=_session_ctx(mock_session),
            ),
        ):
            response = client.post(
                '/api/v1/automations',
                json={
                    'name': 'Test',
                    'schedule': '0 9 * * 5',
                    'prompt': 'Summarize PRs',
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['name'] == 'Test'
        assert data['enabled'] is True
        assert data['trigger_type'] == 'cron'
        assert 'id' in data
        mock_fs.write.assert_called_once()

    def test_create_missing_name(self, client):
        """POST with missing name → 422."""
        response = client.post(
            '/api/v1/automations',
            json={'schedule': '0 9 * * 5', 'prompt': 'Test'},
        )
        assert response.status_code == 422

    def test_create_empty_name(self, client):
        """POST with empty name → 422."""
        response = client.post(
            '/api/v1/automations',
            json={'name': '', 'schedule': '0 9 * * 5', 'prompt': 'Test'},
        )
        assert response.status_code == 422

    def test_create_missing_prompt(self, client):
        """POST with missing prompt → 422."""
        response = client.post(
            '/api/v1/automations',
            json={'name': 'Test', 'schedule': '0 9 * * 5'},
        )
        assert response.status_code == 422

    def test_create_invalid_config_rejected(self, client):
        """POST where validate_config raises → 422."""
        with (
            patch(
                'server.routes.automations.generate_automation_file',
                return_value='__config__ = {}',
            ),
            patch(
                'server.routes.automations.extract_config',
                return_value={},
            ),
            patch(
                'server.routes.automations.validate_config',
                side_effect=ValueError('Invalid cron expression'),
            ),
        ):
            response = client.post(
                '/api/v1/automations',
                json={
                    'name': 'Bad Cron',
                    'schedule': 'not-a-cron',
                    'prompt': 'Test',
                },
            )
        assert response.status_code == 422
        assert 'Invalid automation config' in response.json()['detail']


# --- Test: GET /api/v1/automations/search ---


class TestSearchAutomations:
    def test_list_returns_user_automations(self, client):
        """GET /search → returns only current user's automations."""
        a1 = _make_automation(name='Auto 1')
        a2 = _make_automation(name='Auto 2')

        # Session calls: count query → 2, paginated query → [a1, a2]
        mock_session = _mock_session_with_results([2, [a1, a2]])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/search')

        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 2
        assert len(data['items']) == 2
        assert data['items'][0]['name'] == 'Auto 1'

    def test_list_empty(self, client):
        """GET /search when no automations → empty list."""
        mock_session = _mock_session_with_results([0, []])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/search')

        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert data['items'] == []
        assert data['next_page_id'] is None


# --- Test: GET /api/v1/automations/{id} ---


class TestGetAutomation:
    def test_get_existing(self, client):
        """GET existing automation → 200."""
        auto = _make_automation(automation_id='auto-123')
        mock_session = _mock_session_with_results([auto])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/auto-123')

        assert response.status_code == 200
        assert response.json()['id'] == 'auto-123'

    def test_get_nonexistent(self, client):
        """GET non-existent automation → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/does-not-exist')

        assert response.status_code == status.HTTP_404_NOT_FOUND


# --- Test: PATCH /api/v1/automations/{id} ---


class TestUpdateAutomation:
    def test_update_name_and_enabled(self, client):
        """PATCH with name + enabled → updates fields, returns 200."""
        auto = _make_automation(automation_id='auto-123')
        mock_session = _mock_session_with_results([auto])

        async def fake_refresh(obj):
            obj.name = 'Updated Name'
            obj.enabled = False
            obj.id = 'auto-123'
            obj.trigger_type = 'cron'
            obj.config = auto.config
            obj.last_triggered_at = None
            obj.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            obj.updated_at = datetime(2026, 1, 2, tzinfo=UTC)

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        with (
            patch(
                'server.routes.automations.a_session_maker',
                return_value=_session_ctx(mock_session),
            ),
            patch(
                'server.routes.automations.generate_automation_file',
                return_value='__config__ = {}',
            ),
            patch(
                'server.routes.automations.extract_config',
                return_value=auto.config,
            ),
            patch('server.routes.automations.validate_config'),
            patch('server.routes.automations.file_store') as mock_fs,
        ):
            mock_fs.read.return_value = (
                'conversation.send_message("old prompt")\nconversation.run()'
            )
            response = client.patch(
                '/api/v1/automations/auto-123',
                json={'name': 'Updated Name', 'enabled': False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data['name'] == 'Updated Name'
        assert data['enabled'] is False

    def test_update_nonexistent(self, client):
        """PATCH non-existent → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.patch(
                '/api/v1/automations/nope',
                json={'name': 'X'},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_prompt_regenerates_file(self, client):
        """PATCH with new prompt → re-generates file and uploads."""
        auto = _make_automation(automation_id='auto-123')
        mock_session = _mock_session_with_results([auto])

        async def fake_refresh(obj):
            obj.id = 'auto-123'
            obj.name = auto.name
            obj.enabled = auto.enabled
            obj.trigger_type = 'cron'
            obj.config = auto.config
            obj.last_triggered_at = None
            obj.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            obj.updated_at = datetime(2026, 1, 2, tzinfo=UTC)

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        with (
            patch(
                'server.routes.automations.a_session_maker',
                return_value=_session_ctx(mock_session),
            ),
            patch(
                'server.routes.automations.generate_automation_file',
                return_value='__config__ = {}',
            ) as mock_gen,
            patch(
                'server.routes.automations.extract_config',
                return_value=auto.config,
            ),
            patch('server.routes.automations.validate_config'),
            patch('server.routes.automations.file_store') as mock_fs,
        ):
            response = client.patch(
                '/api/v1/automations/auto-123',
                json={'prompt': 'New prompt text'},
            )

        assert response.status_code == 200
        mock_gen.assert_called_once()
        mock_fs.write.assert_called_once()


# --- Test: DELETE /api/v1/automations/{id} ---


class TestDeleteAutomation:
    def test_delete_existing(self, client):
        """DELETE existing → 204."""
        auto = _make_automation(automation_id='auto-123')
        # First execute: select automation, second: delete runs
        mock_session = _mock_session_with_results([auto, None])

        with (
            patch(
                'server.routes.automations.a_session_maker',
                return_value=_session_ctx(mock_session),
            ),
            patch('server.routes.automations.file_store'),
        ):
            response = client.delete('/api/v1/automations/auto-123')

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_nonexistent(self, client):
        """DELETE non-existent → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.delete('/api/v1/automations/nope')

        assert response.status_code == status.HTTP_404_NOT_FOUND


# --- Test: POST /api/v1/automations/{id}/run ---


class TestManualTrigger:
    def test_manual_trigger_success(self, client):
        """POST .../run on existing automation → 202."""
        auto = _make_automation(automation_id='auto-123')
        mock_session = _mock_session_with_results([auto])

        with (
            patch(
                'server.routes.automations.a_session_maker',
                return_value=_session_ctx(mock_session),
            ),
            patch(
                'server.routes.automations.publish_automation_event',
                new_callable=AsyncMock,
            ) as mock_pub,
        ):
            response = client.post('/api/v1/automations/auto-123/run')

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data['status'] == 'accepted'
        assert 'dedup_key' in data
        assert data['dedup_key'].startswith('manual-auto-123-')
        mock_pub.assert_called_once()

    def test_manual_trigger_nonexistent(self, client):
        """POST .../run on non-existent → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.post('/api/v1/automations/nope/run')

        assert response.status_code == status.HTTP_404_NOT_FOUND


# --- Test: GET /api/v1/automations/{id}/runs ---


class TestListRuns:
    def test_list_runs_success(self, client):
        """GET .../runs → paginated list."""
        r1 = _make_run(run_id='run-1', automation_id='auto-123')
        r2 = _make_run(run_id='run-2', automation_id='auto-123')

        # Calls: ownership check → 'auto-123', count → 2, paginated → [r1, r2]
        mock_session = _mock_session_with_results(['auto-123', 2, [r1, r2]])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/auto-123/runs')

        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 2
        assert len(data['items']) == 2

    def test_list_runs_automation_not_found(self, client):
        """GET .../runs for non-existent automation → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/nope/runs')

        assert response.status_code == status.HTTP_404_NOT_FOUND


# --- Test: GET /api/v1/automations/{id}/runs/{run_id} ---


class TestGetRun:
    def test_get_run_success(self, client):
        """GET single run → 200."""
        run = _make_run(run_id='run-1', automation_id='auto-123')

        # Calls: ownership check → 'auto-123', select run → run
        mock_session = _mock_session_with_results(['auto-123', run])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/auto-123/runs/run-1')

        assert response.status_code == 200
        assert response.json()['id'] == 'run-1'

    def test_get_run_not_found(self, client):
        """GET non-existent run → 404."""
        mock_session = _mock_session_with_results(['auto-123', None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/auto-123/runs/nope')

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_run_automation_not_found(self, client):
        """GET run for non-existent automation → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = client.get('/api/v1/automations/nope/runs/run-1')

        assert response.status_code == status.HTTP_404_NOT_FOUND


# --- Test: User Isolation (security) ---


class TestUserIsolation:
    """Verify that user A cannot access, update, or delete user B's automations.

    The routes filter by user_id from the auth dependency, so automations owned by
    another user should never be returned (the DB query uses WHERE user_id = <caller>).
    We simulate this by having the mock session return None for cross-user lookups.
    """

    @pytest.fixture
    def other_user_app(self):
        """App configured to authenticate as OTHER_USER_ID."""
        app = FastAPI()
        app.include_router(automation_router)

        def mock_get_other_user_id():
            return OTHER_USER_ID

        app.dependency_overrides[get_user_id] = mock_get_other_user_id
        return app

    @pytest.fixture
    def other_client(self, other_user_app):
        return TestClient(other_user_app)

    def test_cannot_get_other_users_automation(self, other_client):
        """User B cannot GET user A's automation → 404."""
        # The query filters by user_id=OTHER_USER_ID, so it won't find user A's row
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = other_client.get('/api/v1/automations/auto-owned-by-a')

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_update_other_users_automation(self, other_client):
        """User B cannot PATCH user A's automation → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = other_client.patch(
                '/api/v1/automations/auto-owned-by-a',
                json={'name': 'Hijacked'},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_delete_other_users_automation(self, other_client):
        """User B cannot DELETE user A's automation → 404."""
        mock_session = _mock_session_with_results([None])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = other_client.delete('/api/v1/automations/auto-owned-by-a')

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_search_returns_empty_for_other_user(self, other_client):
        """User B's search returns empty even if user A has automations."""
        # count=0, rows=[]
        mock_session = _mock_session_with_results([0, []])

        with patch(
            'server.routes.automations.a_session_maker',
            return_value=_session_ctx(mock_session),
        ):
            response = other_client.get('/api/v1/automations/search')

        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert data['items'] == []
