import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.app_server.errors import AuthError
from openhands.app_server.secrets.secrets_router import check_provider_tokens
from openhands.integrations.provider import ProviderToken
from openhands.integrations.service_types import ProviderType
from openhands.server.routes.secrets import (
    app as secrets_router,
)
from openhands.server.routes.settings import _apply_settings_payload
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
    ]
}

_TEST_CONVERSATION_SCHEMA = {
    'sections': [
        {
            'key': 'general',
            'fields': [
                {'key': 'max_iterations', 'secret': False},
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
    if 'llm.api_key' in sdk_vals and 'llm.model' not in sdk_vals:
        sdk_vals['llm.model'] = 'anthropic/claude-sonnet-4-5-20250929'
    return Settings(agent_settings=sdk_vals)


@pytest.fixture(autouse=True)
def allow_short_context_windows():
    with patch.dict(os.environ, {'ALLOW_SHORT_CONTEXT_WINDOWS': 'true'}, clear=False):
        yield


def _agent_value(settings: Settings, key: str) -> Any:
    return settings.get_agent_setting(key)


def _secret_value(settings: Settings, key: str) -> str | None:
    secret = settings.get_secret_agent_setting(key)
    return secret.get_secret_value() if secret else None


# Mock functions to simulate the actual functions in settings.py


def _persisted_value(settings: Settings, key: str) -> Any:
    current: Any = settings.normalized_agent_settings()
    for part in key.split('.'):
        if not isinstance(current, dict):
            raise KeyError(key)
        current = current[part]
    return current


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
        patch('openhands.app_server.utils.dependencies._SESSION_API_KEY', None),
        patch(
            'openhands.app_server.secrets.secrets_router.check_provider_tokens',
            AsyncMock(return_value=None),
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
        'openhands.app_server.secrets.secrets_router.validate_provider_token'
    ) as mock_validate:
        mock_validate.return_value = ProviderType.GITHUB

        await check_provider_tokens(providers, existing_provider_tokens)
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
        'openhands.app_server.secrets.secrets_router.validate_provider_token'
    ) as mock_validate:
        mock_validate.return_value = None

        with pytest.raises(AuthError):
            await check_provider_tokens(providers, existing_provider_tokens)

        mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_check_provider_tokens_wrong_type():
    """Test check_provider_tokens with unsupported provider type."""
    providers = POSTProviderModel(provider_tokens={})
    existing_provider_tokens = {}

    await check_provider_tokens(providers, existing_provider_tokens)


@pytest.mark.asyncio
async def test_check_provider_tokens_no_tokens():
    """Test check_provider_tokens with no tokens."""
    providers = POSTProviderModel(provider_tokens={})
    existing_provider_tokens = {}

    await check_provider_tokens(providers, existing_provider_tokens)


# Tests for _apply_settings_payload (SDK-first settings)
def test_apply_payload_sdk_keys_stored_and_readable():
    """SDK dotted keys should be stored in agent_settings and readable via properties."""
    payload = {
        'llm.model': 'gpt-4',
        'llm.api_key': 'test-api-key',
        'llm.base_url': 'https://api.example.com',
    }

    result = _apply_settings_payload(
        payload, None, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert _persisted_value(result, 'llm.model') == 'gpt-4'
    assert _persisted_value(result, 'llm.api_key') == 'test-api-key'
    assert _persisted_value(result, 'llm.base_url') == 'https://api.example.com'
    # Properties read from agent_settings
    assert _agent_value(result, 'llm.model') == 'gpt-4'
    assert _secret_value(result, 'llm.api_key') == 'test-api-key'
    assert _agent_value(result, 'llm.base_url') == 'https://api.example.com'


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

    result = _apply_settings_payload(
        payload, existing, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert _agent_value(result, 'llm.model') == 'gpt-4'
    assert _secret_value(result, 'llm.api_key') == 'new-api-key'
    assert _agent_value(result, 'llm.base_url') == 'https://new.example.com'


def test_apply_payload_preserves_secrets_when_not_provided():
    """When the API key is not in the payload, the existing value is preserved."""
    existing = _make_settings(
        **{
            'llm.model': 'gpt-3.5',
            'llm.api_key': 'existing-api-key',
        }
    )

    payload = {'llm.model': 'gpt-4'}

    result = _apply_settings_payload(
        payload, existing, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert _agent_value(result, 'llm.model') == 'gpt-4'
    assert _secret_value(result, 'llm.api_key') == 'existing-api-key'
    assert _agent_value(result, 'llm.base_url') is None


def test_apply_payload_mcp_update_preserves_existing_llm_settings():
    existing_settings = Settings(
        llm_model='anthropic/claude-sonnet-4-5-20250929',
        llm_api_key=SecretStr('existing-api-key'),
        llm_base_url='https://my-custom-proxy.example.com',
    )

    result = _apply_settings_payload(
        {
            'mcp_config': {
                'stdio_servers': [
                    {
                        'name': 'my-server',
                        'command': 'npx',
                        'args': ['-y', '@my/mcp-server'],
                        'env': {
                            'API_TOKEN': 'secret123',
                            'ENDPOINT': 'https://example.com',
                        },
                    }
                ]
            }
        },
        existing_settings,
        _TEST_SDK_SCHEMA,
        _TEST_CONVERSATION_SCHEMA,
    )

    assert _agent_value(result, 'llm.model') == 'anthropic/claude-sonnet-4-5-20250929'
    assert _secret_value(result, 'llm.api_key') == 'existing-api-key'
    assert _agent_value(result, 'llm.base_url') == 'https://my-custom-proxy.example.com'


def test_apply_payload_clears_secrets_when_explicitly_null_or_empty():
    """Explicit null/empty secret values should clear existing SDK secrets."""
    existing = _make_settings(**{'llm.api_key': 'existing-api-key'})

    payload = {'llm.api_key': None}
    result = _apply_settings_payload(
        payload, existing, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )
    assert result.agent_settings_values()['llm.api_key'] is None

    payload = {'llm.api_key': ''}
    result = _apply_settings_payload(
        payload, existing, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )
    assert result.agent_settings_values()['llm.api_key'] is None


def test_apply_payload_preserves_explicit_null_non_secret_sdk_resets():
    """Explicit null non-secret SDK values should survive for inherited-settings clearing."""
    existing = _make_settings(
        **{
            'llm.model': 'openai/gpt-4o',
            'llm.base_url': 'https://custom.example/v1',
        }
    )

    result = _apply_settings_payload(
        {'llm.base_url': None}, existing, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert _agent_value(result, 'llm.base_url') is None
    assert _persisted_value(result, 'llm.base_url') is None


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

    result = _apply_settings_payload(
        payload, existing, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert _agent_value(result, 'llm.model') == 'anthropic/claude-sonnet-4-5-20250929'
    assert _secret_value(result, 'llm.api_key') == 'existing-api-key'
    assert _agent_value(result, 'llm.base_url') == 'https://my-custom-proxy.example.com'


def test_apply_payload_non_sdk_flat_keys_applied():
    """Non-SDK flat keys (language, git, etc.) should still be applied normally."""
    payload = {
        'language': 'ja',
        'git_user_name': 'test-user',
    }

    result = _apply_settings_payload(
        payload, None, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert result.language == 'ja'
    assert result.git_user_name == 'test-user'


def test_apply_payload_conversation_settings_stored_top_level():
    """Conversation security settings should be applied as top-level Settings fields."""
    payload = {
        'confirmation_mode': True,
        'security_analyzer': 'llm',
    }

    result = _apply_settings_payload(
        payload, None, _TEST_SDK_SCHEMA, _TEST_CONVERSATION_SCHEMA
    )

    assert result.confirmation_mode is True
    assert result.security_analyzer == 'llm'
    assert 'verification.confirmation_mode' not in result.agent_settings_values()


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

    assert _persisted_value(s, 'llm.model') == 'gpt-4'
    assert _persisted_value(s, 'llm.api_key') == 'my-key'
    assert _persisted_value(s, 'llm.base_url') == 'https://example.com'
    assert _persisted_value(s, 'agent') == 'CodeActAgent'
    assert s.confirmation_mode is True
    assert _agent_value(s, 'llm.model') == 'gpt-4'
    assert _agent_value(s, 'agent') == 'CodeActAgent'


def test_agent_settings_normalized_with_schema_version_and_extras():
    s = Settings(
        llm_model='anthropic/claude-sonnet-4-5-20250929',
        confirmation_mode=True,
        agent_settings={'max_iterations': 64, 'custom.extra': 'keep-me'},
    )

    assert s.raw_agent_settings['schema_version'] == 2
    assert _persisted_value(s, 'llm.model') == 'anthropic/claude-sonnet-4-5-20250929'
    assert s.confirmation_mode is True
    assert s.max_iterations == 64
    assert s.raw_agent_settings['custom.extra'] == 'keep-me'


def test_agent_settings_persistence_strips_secret_values():
    s = Settings(
        llm_model='anthropic/claude-sonnet-4-5-20250929',
        llm_api_key='super-secret',
        agent_settings={'max_iterations': 64},
    )

    persisted = s.normalized_agent_settings(strip_secret_values=True)

    assert persisted['schema_version'] == 2
    assert persisted['llm']['model'] == 'anthropic/claude-sonnet-4-5-20250929'
    assert 'max_iterations' not in persisted
    assert 'api_key' not in persisted['llm']
    assert s.max_iterations == 64


def test_openhands_model_settings_remain_user_facing():
    s = Settings(llm_model='openhands/claude-opus-4-5-20251101')

    assert _persisted_value(s, 'llm.model') == 'litellm_proxy/claude-opus-4-5-20251101'
    assert (
        s.agent_settings_values()['llm.model'] == 'openhands/claude-opus-4-5-20251101'
    )


def test_litellm_proxy_model_settings_migrate_back_to_openhands_prefix():
    s = Settings(agent_settings={'llm.model': 'litellm_proxy/claude-opus-4-5-20251101'})

    assert _persisted_value(s, 'llm.model') == 'litellm_proxy/claude-opus-4-5-20251101'
    assert (
        s.agent_settings_values()['llm.model'] == 'openhands/claude-opus-4-5-20251101'
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
