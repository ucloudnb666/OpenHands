import warnings
from unittest.mock import patch

from pydantic import SecretStr

from openhands.app_server.settings.settings_router import convert_to_settings
from openhands.core.config.llm_config import LLMConfig
from openhands.core.config.mcp_config import MCPConfig as LegacyMCPConfig
from openhands.core.config.openhands_config import OpenHandsConfig
from openhands.core.config.sandbox_config import SandboxConfig
from openhands.core.config.security_config import SecurityConfig
from openhands.storage.data_models.settings import Settings


def test_settings_from_config():
    # Mock configuration
    mock_app_config = OpenHandsConfig(
        default_agent='test-agent',
        max_iterations=100,
        security=SecurityConfig(
            security_analyzer='llm',
            confirmation_mode=True,
        ),
        llms={
            'llm': LLMConfig(
                model='test-model',
                api_key=SecretStr('test-key'),
                base_url='https://test.example.com',
            )
        },
        sandbox=SandboxConfig(remote_runtime_resource_factor=2),
    )

    with patch(
        'openhands.storage.data_models.settings.load_openhands_config',
        return_value=mock_app_config,
    ):
        settings = Settings.from_config()

        assert settings is not None
        assert settings.language == 'en'
        assert settings.get_agent_setting('agent') == 'test-agent'
        assert settings.conversation_settings.max_iterations == 100
        assert settings.conversation_settings.security_analyzer == 'llm'
        assert settings.conversation_settings.confirmation_mode is True
        assert settings.get_agent_setting('llm.model') == 'test-model'
        assert (
            settings.get_secret_agent_setting('llm.api_key').get_secret_value()
            == 'test-key'
        )
        assert settings.get_agent_setting('llm.base_url') == 'https://test.example.com'
        assert settings.remote_runtime_resource_factor == 2
        assert not settings.secrets_store.provider_tokens


def test_settings_from_config_no_api_key():
    # Mock configuration without API key
    mock_app_config = OpenHandsConfig(
        default_agent='test-agent',
        max_iterations=100,
        security=SecurityConfig(
            security_analyzer='llm',
            confirmation_mode=True,
        ),
        llms={
            'llm': LLMConfig(
                model='test-model', api_key=None, base_url='https://test.example.com'
            )
        },
        sandbox=SandboxConfig(remote_runtime_resource_factor=2),
    )

    with patch(
        'openhands.storage.data_models.settings.load_openhands_config',
        return_value=mock_app_config,
    ):
        settings = Settings.from_config()
        assert settings is None


def test_settings_handles_sensitive_data():
    settings = Settings(
        language='en',
        agent='test-agent',
        max_iterations=100,
        security_analyzer='llm',
        confirmation_mode=True,
        llm_model='test-model',
        llm_api_key='test-key',
        llm_base_url='https://test.example.com',
        remote_runtime_resource_factor=2,
    )

    llm_api_key = settings.get_secret_agent_setting('llm.api_key')
    assert str(llm_api_key) == '**********'
    assert llm_api_key.get_secret_value() == 'test-key'


def test_convert_to_settings():
    settings_with_token_data = Settings(
        llm_model='test-model',
        llm_api_key='test-key',
    )

    settings = convert_to_settings(settings_with_token_data)

    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == 'test-key'


def test_settings_preserve_agent_settings():
    settings = Settings(
        agent_settings={
            'llm.model': 'test-model',
            'llm.api_key': 'test-key',
            'verification.critic_enabled': True,
            'verification.critic_mode': 'all_actions',
            'llm.litellm_extra_body': {'metadata': {'tier': 'pro'}},
        },
    )

    assert (
        settings.get_secret_agent_setting('llm.api_key').get_secret_value()
        == 'test-key'
    )
    persisted = settings.normalized_agent_settings()

    assert persisted['schema_version'] == 1
    assert persisted['llm']['model'] == 'test-model'
    assert persisted['llm']['api_key'] == 'test-key'
    assert persisted['verification']['critic_enabled'] is True
    assert persisted['verification']['critic_mode'] == 'all_actions'
    assert persisted['llm']['litellm_extra_body'] == {'metadata': {'tier': 'pro'}}


def test_settings_to_agent_settings_uses_agent_vals():
    settings = Settings(
        agent_settings={
            'llm.model': 'sdk-model',
            'llm.base_url': 'https://sdk.example.com',
            'llm.litellm_extra_body': {'metadata': {'tier': 'enterprise'}},
            'condenser.enabled': False,
            'condenser.max_size': 88,
            'verification.critic_enabled': True,
            'verification.critic_mode': 'all_actions',
        },
    )

    agent_settings = settings.to_agent_settings()

    assert agent_settings.llm.model == 'sdk-model'
    assert agent_settings.llm.base_url == 'https://sdk.example.com'
    assert agent_settings.llm.litellm_extra_body == {'metadata': {'tier': 'enterprise'}}
    assert agent_settings.condenser.enabled is False
    assert agent_settings.condenser.max_size == 88
    assert agent_settings.verification.critic_enabled is True
    assert agent_settings.verification.critic_mode == 'all_actions'


def test_settings_agent_settings_keeps_sdk_mcp_shape_canonical():
    settings = Settings(
        agent_settings={
            'llm.model': 'sdk-model',
            'mcp_config': {
                'sse_servers': [{'url': 'https://example.com/sse'}],
            },
        },
    )

    assert settings.raw_agent_settings['mcp_config'] == {
        'mcpServers': {'sse_0': {'transport': 'sse', 'url': 'https://example.com/sse'}}
    }
    assert settings.agent_settings_values()['mcp_config'] == {
        'mcpServers': {'sse_0': {'transport': 'sse', 'url': 'https://example.com/sse'}}
    }
    assert settings.to_legacy_mcp_config() == LegacyMCPConfig.model_validate(
        {'sse_servers': [{'url': 'https://example.com/sse'}]}
    )


def test_settings_set_agent_setting_keeps_sdk_mcp_shape_for_persistence():
    settings = Settings(agent_settings={'llm.model': 'sdk-model'})

    settings.set_agent_setting(
        'mcp_config',
        {
            'mcpServers': {
                'custom': {'transport': 'http', 'url': 'https://example.com/mcp'}
            }
        },
    )

    assert settings.raw_agent_settings['mcp_config'] == {
        'mcpServers': {
            'custom': {
                'transport': 'http',
                'url': 'https://example.com/mcp',
            }
        }
    }
    assert settings.agent_settings_values()['mcp_config'] == {
        'mcpServers': {
            'custom': {
                'transport': 'http',
                'url': 'https://example.com/mcp',
            }
        }
    }
    assert settings.to_legacy_mcp_config() == LegacyMCPConfig.model_validate(
        {'shttp_servers': [{'url': 'https://example.com/mcp', 'timeout': 60}]}
    )


def test_settings_no_pydantic_frozen_field_warning():
    """Test that Settings model does not trigger Pydantic UnsupportedFieldAttributeWarning.

    This test ensures that the 'frozen' parameter is not incorrectly used in Field()
    definitions, which would cause warnings in Pydantic v2 for union types.
    See: https://github.com/All-Hands-AI/infra/issues/860
    """
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')

        # Re-import to trigger any warnings during model definition
        import importlib

        import openhands.storage.data_models.settings

        importlib.reload(openhands.storage.data_models.settings)

        # Check for warnings containing 'frozen' which would indicate
        # incorrect usage of frozen=True in Field()
        frozen_warnings = [
            warning for warning in w if 'frozen' in str(warning.message).lower()
        ]

        assert len(frozen_warnings) == 0, (
            f'Pydantic frozen field warnings found: {[str(w.message) for w in frozen_warnings]}'
        )
