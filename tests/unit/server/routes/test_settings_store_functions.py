import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.core.config.mcp_config import MCPConfig, MCPStdioServerConfig
from openhands.integrations.provider import ProviderToken
from openhands.integrations.service_types import ProviderType
from openhands.server.routes.secrets import (
    app as secrets_router,
)
from openhands.server.routes.secrets import (
    check_provider_tokens,
)
from openhands.server.routes.settings import _apply_settings_payload, store_llm_settings
from openhands.server.settings import POSTProviderModel
from openhands.storage import get_file_store
from openhands.storage.data_models.secrets import Secrets
from openhands.storage.data_models.settings import Settings
from openhands.storage.secrets.file_secrets_store import FileSecretsStore

# Minimal SDK schema fixture for tests.
_TEST_SDK_SCHEMA = {
    'sections': [
        {
            'key': 'llm',
            'fields': [
                {'key': 'llm.model', 'secret': False},
                {'key': 'llm.api_key', 'secret': True},
                {'key': 'llm.base_url', 'secret': False},
            ],
        },
        {
            'key': 'condenser',
            'fields': [
                {'key': 'condenser.enabled', 'secret': False},
                {'key': 'condenser.max_size', 'secret': False},
            ],
        },
        {
            'key': 'verification',
            'fields': [
                {'key': 'verification.confirmation_mode', 'secret': False},
                {'key': 'verification.security_analyzer', 'secret': False},
            ],
        },
    ]
}


def _make_settings(**sdk_vals: Any) -> Settings:
    """Helper to create Settings with agent_settings."""
    return Settings(agent_settings=sdk_vals)


# Mock functions to simulate the actual functions in settings.py
async def get_settings_store(request):
    """Mock function to get settings store."""
    return MagicMock()


@pytest.fixture
def test_client():
    # Create a test client with a FastAPI app that includes the secrets router
    # This is necessary because TestClient with APIRouter directly doesn't set up
    # the full middleware stack in newer FastAPI versions (0.118.0+)
    test_app = FastAPI()
    test_app.include_router(secrets_router)

    with (
        patch.dict(os.environ, {'SESSION_API_KEY': ''}, clear=False),
        patch('openhands.server.dependencies._SESSION_API_KEY', None),
        patch(
            'openhands.server.routes.secrets.check_provider_tokens',
            AsyncMock(return_value=''),
        ),
    ):
        client = TestClient(test_app)
        yield client


@pytest.fixture
def temp_dir(tmp_path_factory: pytest.TempPathFactory) -> str:
    return str(tmp_path_factory.mktemp('secrets_store'))


@pytest.fixture
def file_secrets_store(temp_dir):
    file_store = get_file_store('local', temp_dir)
    store = FileSecretsStore(file_store)
    with patch(
        'openhands.storage.secrets.file_secrets_store.FileSecretsStore.get_instance',
        AsyncMock(return_value=store),
    ):
        yield store


# Tests for check_provider_tokens
@pytest.mark.asyncio
async def test_check_provider_tokens_valid():
    """Test check_provider_tokens with valid tokens."""
    provider_token = ProviderToken(token=SecretStr('valid-token'))
    providers = POSTProviderModel(provider_tokens={ProviderType.GITHUB: provider_token})

    # Empty existing provider tokens
    existing_provider_tokens = {}

    # Mock the validate_provider_token function to return GITHUB for valid tokens
    with patch(
        'openhands.server.routes.secrets.validate_provider_token'
    ) as mock_validate:
        mock_validate.return_value = ProviderType.GITHUB

        result = await check_provider_tokens(providers, existing_provider_tokens)

        # Should return empty string for valid token
        assert result == ''
        mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_check_provider_tokens_invalid():
    """Test check_provider_tokens with invalid tokens."""
    provider_token = ProviderToken(token=SecretStr('invalid-token'))
    providers = POSTProviderModel(provider_tokens={ProviderType.GITHUB: provider_token})

    # Empty existing provider tokens
    existing_provider_tokens = {}

    # Mock the validate_provider_token function to return None for invalid tokens
    with patch(
        'openhands.server.routes.secrets.validate_provider_token'
    ) as mock_validate:
        mock_validate.return_value = None

        result = await check_provider_tokens(providers, existing_provider_tokens)

        # Should return error message for invalid token
        assert 'Invalid token' in result
        mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_check_provider_tokens_wrong_type():
    """Test check_provider_tokens with unsupported provider type."""
    providers = POSTProviderModel(provider_tokens={})
    existing_provider_tokens = {}

    result = await check_provider_tokens(providers, existing_provider_tokens)
    assert result == ''


@pytest.mark.asyncio
async def test_check_provider_tokens_no_tokens():
    """Test check_provider_tokens with no tokens."""
    providers = POSTProviderModel(provider_tokens={})
    existing_provider_tokens = {}

    result = await check_provider_tokens(providers, existing_provider_tokens)
    assert result == ''


# Tests for _apply_settings_payload (SDK-first settings)
def test_apply_payload_sdk_keys_stored_and_readable():
    """SDK dotted keys should be stored in agent_settings and readable via properties."""
    payload = {
        'llm.model': 'gpt-4',
        'llm.api_key': 'test-api-key',
        'llm.base_url': 'https://api.example.com',
    }

    result = _apply_settings_payload(payload, None, _TEST_SDK_SCHEMA)

    assert result.agent_settings['llm.model'] == 'gpt-4'
    assert result.agent_settings['llm.api_key'] == 'test-api-key'
    assert result.agent_settings['llm.base_url'] == 'https://api.example.com'
    # Properties read from agent_settings
    assert result.llm_model == 'gpt-4'
    assert result.llm_api_key.get_secret_value() == 'test-api-key'
    assert result.llm_base_url == 'https://api.example.com'


def test_apply_payload_updates_existing():
    """SDK keys should update existing settings."""
    existing = _make_settings(
        **{
            'llm.model': 'gpt-3.5',
            'llm.api_key': 'old-api-key',
            'llm.base_url': 'https://old.example.com',
        }
    )

    payload = {
        'llm.model': 'gpt-4',
        'llm.api_key': 'new-api-key',
        'llm.base_url': 'https://new.example.com',
    }

    result = _apply_settings_payload(payload, existing, _TEST_SDK_SCHEMA)

    assert result.llm_model == 'gpt-4'
    assert result.llm_api_key.get_secret_value() == 'new-api-key'
    assert result.llm_base_url == 'https://new.example.com'


def test_apply_payload_preserves_secrets_when_not_provided():
    """When the API key is not in the payload, the existing value is preserved."""
    existing = _make_settings(
        **{
            'llm.model': 'gpt-3.5',
            'llm.api_key': 'existing-api-key',
        }
    )

    payload = {'llm.model': 'gpt-4'}

    result = _apply_settings_payload(payload, existing, _TEST_SDK_SCHEMA)

    assert result.llm_model == 'gpt-4'
    assert result.llm_api_key.get_secret_value() == 'existing-api-key'
    assert result.llm_base_url is None


@pytest.mark.asyncio
async def test_store_llm_settings_advanced_view_clear_removes_base_url():
    settings = Settings(
        llm_model='gpt-4',
        llm_base_url='',
    )

    existing_settings = Settings(
        llm_model='gpt-4',
        llm_api_key=SecretStr('my-api-key'),
        llm_base_url='https://my-custom-proxy.example.com',
    )

    result = await store_llm_settings(settings, existing_settings)

    assert result.llm_base_url is None


@pytest.mark.asyncio
async def test_store_llm_settings_mcp_update_preserves_base_url():
    settings = Settings(
        mcp_config=MCPConfig(
            stdio_servers=[
                MCPStdioServerConfig(
                    name='my-server',
                    command='npx',
                    args=['-y', '@my/mcp-server'],
                    env={
                        'API_TOKEN': 'secret123',
                        'ENDPOINT': 'https://example.com',
                    },
                )
            ],
        ),
    )

    existing_settings = Settings(
        llm_model='anthropic/claude-sonnet-4-5-20250929',
        llm_api_key=SecretStr('existing-api-key'),
        llm_base_url='https://my-custom-proxy.example.com',
    )

    result = await store_llm_settings(settings, existing_settings)

    assert result.llm_model == 'anthropic/claude-sonnet-4-5-20250929'
    assert result.llm_api_key.get_secret_value() == 'existing-api-key'
    assert result.llm_base_url == 'https://my-custom-proxy.example.com'


def test_apply_payload_preserves_secrets_when_null():
    """Null/empty secret values in the payload should not overwrite existing secrets."""
    existing = _make_settings(**{'llm.api_key': 'existing-api-key'})

    payload = {'llm.api_key': None}
    result = _apply_settings_payload(payload, existing, _TEST_SDK_SCHEMA)
    assert result.agent_settings['llm.api_key'] == 'existing-api-key'

    payload = {'llm.api_key': ''}
    result = _apply_settings_payload(payload, existing, _TEST_SDK_SCHEMA)
    assert result.agent_settings['llm.api_key'] == 'existing-api-key'


def test_apply_payload_mcp_preserves_llm_settings():
    """Non-LLM payloads (e.g. MCP config) should not affect existing LLM settings."""
    existing = _make_settings(
        **{
            'llm.model': 'anthropic/claude-sonnet-4-5-20250929',
            'llm.api_key': 'existing-api-key',
            'llm.base_url': 'https://my-custom-proxy.example.com',
        }
    )

    payload = {
        'mcp_config': {
            'stdio_servers': [
                {
                    'name': 'my-server',
                    'command': 'npx',
                    'args': ['-y', '@my/mcp-server'],
                }
            ],
        },
    }

    result = _apply_settings_payload(payload, existing, _TEST_SDK_SCHEMA)

    assert result.llm_model == 'anthropic/claude-sonnet-4-5-20250929'
    assert result.llm_api_key.get_secret_value() == 'existing-api-key'
    assert result.llm_base_url == 'https://my-custom-proxy.example.com'


def test_apply_payload_non_sdk_flat_keys_applied():
    """Non-SDK flat keys (language, git, etc.) should still be applied normally."""
    payload = {
        'language': 'ja',
        'git_user_name': 'test-user',
    }

    result = _apply_settings_payload(payload, None, _TEST_SDK_SCHEMA)

    assert result.language == 'ja'
    assert result.git_user_name == 'test-user'


def test_apply_payload_verification_stored_and_readable():
    """Verification SDK keys are stored and readable via properties."""
    payload = {
        'verification.confirmation_mode': True,
        'verification.security_analyzer': 'llm',
    }

    result = _apply_settings_payload(payload, None, _TEST_SDK_SCHEMA)

    assert result.confirmation_mode is True
    assert result.security_analyzer == 'llm'
    assert result.agent_settings['verification.confirmation_mode'] is True


def test_legacy_flat_fields_migrate_to_agent_vals():
    """Loading a Settings with legacy flat fields should migrate to agent_settings."""
    s = Settings(
        **{
            'llm_model': 'gpt-4',
            'llm_api_key': 'my-key',
            'llm_base_url': 'https://example.com',
            'agent': 'CodeActAgent',
            'confirmation_mode': True,
        }
    )

    assert s.agent_settings['llm.model'] == 'gpt-4'
    assert s.agent_settings['llm.api_key'] == 'my-key'
    assert s.agent_settings['llm.base_url'] == 'https://example.com'
    assert s.agent_settings['agent'] == 'CodeActAgent'
    assert s.agent_settings['verification.confirmation_mode'] is True
    # Properties work
    assert s.llm_model == 'gpt-4'
    assert s.agent == 'CodeActAgent'


def test_agent_settings_normalized_with_schema_version_and_extras():
    s = Settings(
        llm_model='anthropic/claude-sonnet-4-5-20250929',
        confirmation_mode=True,
        agent_settings={'max_iterations': 64, 'custom.extra': 'keep-me'},
    )

    assert s.agent_settings['schema_version'] == 1
    assert s.agent_settings['llm.model'] == 'anthropic/claude-sonnet-4-5-20250929'
    assert s.agent_settings['verification.confirmation_mode'] is True
    assert s.agent_settings['max_iterations'] == 64
    assert s.agent_settings['custom.extra'] == 'keep-me'


def test_agent_settings_persistence_strips_secret_values():
    s = Settings(
        llm_model='anthropic/claude-sonnet-4-5-20250929',
        llm_api_key='super-secret',
        agent_settings={'max_iterations': 64},
    )

    persisted = s.normalized_agent_settings(strip_secret_values=True)

    assert persisted['schema_version'] == 1
    assert persisted['llm.model'] == 'anthropic/claude-sonnet-4-5-20250929'
    assert persisted['max_iterations'] == 64
    assert 'llm.api_key' not in persisted


def test_openhands_model_settings_remain_user_facing():
    s = Settings(llm_model='openhands/claude-opus-4-5-20251101')

    assert s.agent_settings['llm.model'] == 'openhands/claude-opus-4-5-20251101'
    assert s.normalized_agent_settings(strip_secret_values=True)['llm.model'] == (
        'openhands/claude-opus-4-5-20251101'
    )


def test_litellm_proxy_model_settings_migrate_back_to_openhands_prefix():
    s = Settings(agent_settings={'llm.model': 'litellm_proxy/claude-opus-4-5-20251101'})

    assert s.agent_settings['llm.model'] == 'openhands/claude-opus-4-5-20251101'
    assert s.normalized_agent_settings(strip_secret_values=True)['llm.model'] == (
        'openhands/claude-opus-4-5-20251101'
    )


# Tests for store_provider_tokens
@pytest.mark.asyncio
async def test_store_provider_tokens_new_tokens(test_client, file_secrets_store):
    """Test store_provider_tokens with new tokens."""
    provider_tokens = {'provider_tokens': {'github': {'token': 'new-token'}}}

    # Mock the settings store
    mock_store = MagicMock()
    mock_store.load = AsyncMock(return_value=None)  # No existing settings

    Secrets()

    user_secrets = await file_secrets_store.store(Secrets())

    response = test_client.post('/api/add-git-providers', json=provider_tokens)
    assert response.status_code == 200

    user_secrets = await file_secrets_store.load()

    assert (
        user_secrets.provider_tokens[ProviderType.GITHUB].token.get_secret_value()
        == 'new-token'
    )


@pytest.mark.asyncio
async def test_store_provider_tokens_update_existing(test_client, file_secrets_store):
    """Test store_provider_tokens updates existing tokens."""
    # Create existing settings with a GitHub token
    github_token = ProviderToken(token=SecretStr('old-token'))
    provider_tokens = {ProviderType.GITHUB: github_token}

    # Create a Secrets with the provider tokens
    user_secrets = Secrets(provider_tokens=provider_tokens)

    await file_secrets_store.store(user_secrets)

    response = test_client.post(
        '/api/add-git-providers',
        json={'provider_tokens': {'github': {'token': 'updated-token'}}},
    )

    assert response.status_code == 200

    user_secrets = await file_secrets_store.load()

    assert (
        user_secrets.provider_tokens[ProviderType.GITHUB].token.get_secret_value()
        == 'updated-token'
    )


@pytest.mark.asyncio
async def test_store_provider_tokens_keep_existing(test_client, file_secrets_store):
    """Test store_provider_tokens keeps existing tokens when empty string provided."""
    # Create existing secrets with a GitHub token
    github_token = ProviderToken(token=SecretStr('existing-token'))
    provider_tokens = {ProviderType.GITHUB: github_token}
    user_secrets = Secrets(provider_tokens=provider_tokens)

    await file_secrets_store.store(user_secrets)

    response = test_client.post(
        '/api/add-git-providers',
        json={'provider_tokens': {'github': {'token': ''}}},
    )
    assert response.status_code == 200

    user_secrets = await file_secrets_store.load()

    assert (
        user_secrets.provider_tokens[ProviderType.GITHUB].token.get_secret_value()
        == 'existing-token'
    )
