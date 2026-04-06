import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.integrations.provider import ProviderToken, ProviderType
from openhands.integrations.service_types import UserGitInfo
from openhands.server.app import app
from openhands.server.user_auth.user_auth import UserAuth
from openhands.storage.data_models.secrets import Secrets
from openhands.storage.memory import InMemoryFileStore
from openhands.storage.secrets.secrets_store import SecretsStore
from openhands.storage.settings.file_settings_store import FileSettingsStore
from openhands.storage.settings.settings_store import SettingsStore


class MockUserAuth(UserAuth):
    """Mock implementation of UserAuth for testing."""

    def __init__(self):
        self._settings = None
        self._settings_store = MagicMock()
        self._settings_store.load = AsyncMock(return_value=None)
        self._settings_store.store = AsyncMock()

    async def get_user_id(self) -> str | None:
        return 'test-user'

    async def get_user_email(self) -> str | None:
        return 'test-email@whatever.com'

    async def get_access_token(self) -> SecretStr | None:
        return SecretStr('test-token')

    async def get_provider_tokens(
        self,
    ) -> dict[ProviderType, ProviderToken] | None:  # noqa: E501
        return None

    async def get_user_settings_store(self) -> SettingsStore | None:
        return self._settings_store

    async def get_secrets_store(self) -> SecretsStore | None:
        return None

    async def get_secrets(self) -> Secrets | None:
        return None

    async def get_mcp_api_key(self) -> str | None:
        return None

    async def get_user_git_info(self) -> UserGitInfo | None:
        return None

    @classmethod
    async def get_instance(cls, request: Request) -> UserAuth:
        return MockUserAuth()

    @classmethod
    async def get_for_user(cls, user_id: str) -> UserAuth:
        return MockUserAuth()


@pytest.fixture
def test_client():
    # Create a test client
    with (
        patch.dict(
            os.environ,
            {'SESSION_API_KEY': '', 'ALLOW_SHORT_CONTEXT_WINDOWS': 'true'},
            clear=False,
        ),
        patch('openhands.app_server.utils.dependencies._SESSION_API_KEY', None),
        patch(
            'openhands.server.user_auth.user_auth.UserAuth.get_instance',
            return_value=MockUserAuth(),
        ),
        patch(
            'openhands.storage.settings.file_settings_store.FileSettingsStore.get_instance',
            AsyncMock(return_value=FileSettingsStore(InMemoryFileStore())),
        ),
    ):
        client = TestClient(app)
        yield client


def test_get_agent_settings_schema_includes_verification_section(test_client):
    response = test_client.get('/api/settings/schema')

    assert response.status_code == 200
    schema = response.json()
    section_keys = [s['key'] for s in schema['sections']]
    assert 'verification' in section_keys
    section = next(s for s in schema['sections'] if s['key'] == 'verification')
    field_keys = [f['key'] for f in section['fields']]
    assert 'verification.confirmation_mode' in field_keys
    assert 'verification.security_analyzer' in field_keys
    assert 'verification.critic_enabled' in field_keys


@pytest.mark.asyncio
async def test_settings_api_endpoints(test_client):
    """Test that the settings API endpoints work with the new auth system."""
    agent_settings_schema = {
        'model_name': 'AgentSettings',
        'sections': [
            {
                'key': 'llm',
                'label': 'LLM',
                'fields': [
                    {
                        'key': 'llm.model',
                        'value_type': 'string',
                        'prominence': 'critical',
                    },
                    {
                        'key': 'llm.base_url',
                        'value_type': 'string',
                        'prominence': 'major',
                    },
                    {
                        'key': 'llm.timeout',
                        'value_type': 'integer',
                        'prominence': 'minor',
                    },
                    {
                        'key': 'llm.litellm_extra_body',
                        'value_type': 'object',
                        'prominence': 'minor',
                    },
                    {
                        'key': 'llm.api_key',
                        'value_type': 'string',
                        'prominence': 'critical',
                        'secret': True,
                    },
                ],
            },
            {
                'key': 'verification',
                'label': 'Verification',
                'fields': [
                    {
                        'key': 'verification.critic_enabled',
                        'value_type': 'boolean',
                        'prominence': 'critical',
                    },
                    {
                        'key': 'verification.critic_mode',
                        'value_type': 'string',
                        'prominence': 'minor',
                    },
                    {
                        'key': 'verification.enable_iterative_refinement',
                        'value_type': 'boolean',
                        'prominence': 'major',
                    },
                    {
                        'key': 'verification.critic_threshold',
                        'value_type': 'number',
                        'prominence': 'minor',
                    },
                    {
                        'key': 'verification.max_refinement_iterations',
                        'value_type': 'integer',
                        'prominence': 'minor',
                    },
                    {
                        'key': 'verification.confirmation_mode',
                        'value_type': 'boolean',
                        'prominence': 'major',
                    },
                    {
                        'key': 'verification.security_analyzer',
                        'value_type': 'string',
                        'prominence': 'major',
                    },
                ],
            },
        ],
    }

    # Test data with remote_runtime_resource_factor
    settings_data = {
        'language': 'en',
        'agent': 'test-agent',
        'max_iterations': 100,
        'security_analyzer': 'default',
        'confirmation_mode': True,
        'llm.model': 'test-model',
        'llm.api_key': 'test-key',
        'llm.base_url': 'https://test.com',
        'llm.timeout': 123,
        'llm.litellm_extra_body': {'metadata': {'tier': 'pro'}},
        'remote_runtime_resource_factor': 2,
        'verification.critic_enabled': True,
        'verification.critic_mode': 'all_actions',
        'verification.enable_iterative_refinement': True,
        'verification.critic_threshold': 0.7,
        'verification.max_refinement_iterations': 4,
        'verification.confirmation_mode': True,
        'verification.security_analyzer': 'llm',
    }

    with patch(
        'openhands.server.routes.settings._get_agent_settings_schema',
        return_value=agent_settings_schema,
    ):
        # Make the POST request to store settings
        response = test_client.post('/api/settings', json=settings_data)

        # We're not checking the exact response, just that it doesn't error
        assert response.status_code == 200

        # Test the GET settings endpoint
        response = test_client.get('/api/settings')
        assert response.status_code == 200
        response_data = response.json()
        assert 'agent_settings_schema' not in response_data
        vals = response_data['agent_settings']
        assert vals['llm.model'] == 'test-model'
        assert vals['llm.timeout'] == 123
        assert vals['llm.litellm_extra_body'] == {'metadata': {'tier': 'pro'}}
        assert vals['verification.critic_enabled'] is True
        assert vals['verification.critic_mode'] == 'all_actions'
        assert vals['verification.enable_iterative_refinement'] is True
        assert vals['verification.critic_threshold'] == 0.7
        assert vals['verification.max_refinement_iterations'] == 4
        assert vals['verification.confirmation_mode'] is True
        assert vals['verification.security_analyzer'] == 'llm'
        assert vals['llm.api_key'] == '<hidden>'

        # Test updating with partial settings
        partial_settings = {
            'language': 'fr',
            'llm_model': None,  # Should preserve existing value
            'llm_api_key': None,  # Should preserve existing value
        }

        response = test_client.post('/api/settings', json=partial_settings)
        assert response.status_code == 200

        response = test_client.get('/api/settings')
        assert response.status_code == 200
        assert response.json()['agent_settings']['llm.timeout'] == 123

        # Test the unset-provider-tokens endpoint
        response = test_client.post('/api/unset-provider-tokens')
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_saving_settings_with_frozen_secrets_store(test_client):
    """Regression: POSTing settings must not fail with `secrets_store`.

    See https://github.com/OpenHands/OpenHands/issues/13306.
    """
    settings_data = {
        'language': 'en',
        'llm.model': 'gpt-4',
        'secrets_store': {'provider_tokens': {}},
    }
    response = test_client.post('/api/settings', json=settings_data)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_api_key_preservation(test_client):
    """Test that search_api_key is preserved when sending an empty string."""
    # 1. Set initial settings with a search API key (use SDK dotted keys)
    initial_settings = {
        'search_api_key': 'initial-secret-key',
        'llm.model': 'gpt-4',
    }
    response = test_client.post('/api/settings', json=initial_settings)
    assert response.status_code == 200

    # Verify key is set
    response = test_client.get('/api/settings')
    assert response.status_code == 200
    assert response.json()['search_api_key_set'] is True

    # 2. Update settings with EMPTY search API key (simulating the frontend bug)
    # and changing another field via SDK key
    update_settings = {
        'search_api_key': '',
        'llm.model': 'claude-3-opus',
    }
    response = test_client.post('/api/settings', json=update_settings)
    assert response.status_code == 200

    # 3. Verify the key was NOT wiped out (The Critical Check)
    response = test_client.get('/api/settings')
    assert response.status_code == 200
    assert response.json()['search_api_key_set'] is True
    # Verify the SDK value updated
    assert response.json()['agent_settings']['llm.model'] == 'claude-3-opus'


@pytest.mark.asyncio
async def test_disabled_skills_persistence(test_client):
    """Test that disabled_skills can be saved and retrieved via the settings API."""
    response = test_client.post(
        '/api/settings',
        json={
            'disabled_skills': ['skill_a', 'skill_b'],
            'llm.model': 'test-model',
        },
    )
    assert response.status_code == 200

    response = test_client.get('/api/settings')
    assert response.status_code == 200
    data = response.json()
    assert data['disabled_skills'] == ['skill_a', 'skill_b']

    response = test_client.post(
        '/api/settings',
        json={
            'disabled_skills': ['skill_c'],
        },
    )
    assert response.status_code == 200

    response = test_client.get('/api/settings')
    assert response.status_code == 200
    data = response.json()
    assert data['disabled_skills'] == ['skill_c']

    response = test_client.post(
        '/api/settings',
        json={
            'disabled_skills': [],
        },
    )
    assert response.status_code == 200

    response = test_client.get('/api/settings')
    assert response.status_code == 200
    data = response.json()
    assert data['disabled_skills'] == []
