import warnings
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from openhands.core.config.llm_config import LLMConfig
from openhands.core.config.openhands_config import OpenHandsConfig
from openhands.core.config.sandbox_config import SandboxConfig
from openhands.core.config.security_config import SecurityConfig
from openhands.server.routes.settings import convert_to_settings
from openhands.storage.data_models.settings import MarketplaceRegistration, Settings


def test_settings_from_config():
    # Mock configuration
    mock_app_config = OpenHandsConfig(
        default_agent='test-agent',
        max_iterations=100,
        security=SecurityConfig(
            security_analyzer='test-analyzer',
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
        assert settings.agent == 'test-agent'
        assert settings.max_iterations == 100
        assert settings.security_analyzer == 'test-analyzer'
        assert settings.confirmation_mode is True
        assert settings.llm_model == 'test-model'
        assert settings.llm_api_key.get_secret_value() == 'test-key'
        assert settings.llm_base_url == 'https://test.example.com'
        assert settings.remote_runtime_resource_factor == 2
        assert not settings.secrets_store.provider_tokens


def test_settings_from_config_no_api_key():
    # Mock configuration without API key
    mock_app_config = OpenHandsConfig(
        default_agent='test-agent',
        max_iterations=100,
        security=SecurityConfig(
            security_analyzer='test-analyzer',
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
        security_analyzer='test-analyzer',
        confirmation_mode=True,
        llm_model='test-model',
        llm_api_key='test-key',
        llm_base_url='https://test.example.com',
        remote_runtime_resource_factor=2,
    )

    assert str(settings.llm_api_key) == '**********'
    assert settings.llm_api_key.get_secret_value() == 'test-key'


def test_convert_to_settings():
    settings_with_token_data = Settings(
        llm_api_key='test-key',
    )

    settings = convert_to_settings(settings_with_token_data)

    assert settings.llm_api_key.get_secret_value() == 'test-key'


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


# --- Tests for MarketplaceRegistration ---


class TestMarketplaceRegistration:
    """Tests for MarketplaceRegistration model."""

    def test_basic_registration(self):
        """Test creating a basic marketplace registration."""
        reg = MarketplaceRegistration(
            name='test-marketplace',
            source='github:owner/repo',
        )
        assert reg.name == 'test-marketplace'
        assert reg.source == 'github:owner/repo'
        assert reg.ref is None
        assert reg.repo_path is None
        assert reg.auto_load is None

    def test_registration_with_auto_load(self):
        """Test registration with auto_load='all'."""
        reg = MarketplaceRegistration(
            name='public',
            source='github:OpenHands/skills',
            auto_load='all',
        )
        assert reg.auto_load == 'all'

    def test_registration_with_ref(self):
        """Test registration with specific ref."""
        reg = MarketplaceRegistration(
            name='versioned',
            source='github:owner/repo',
            ref='v1.0.0',
        )
        assert reg.ref == 'v1.0.0'

    def test_registration_with_repo_path(self):
        """Test registration with repo_path for monorepos."""
        reg = MarketplaceRegistration(
            name='monorepo-marketplace',
            source='github:acme/monorepo',
            repo_path='marketplaces/internal',
        )
        assert reg.repo_path == 'marketplaces/internal'

    def test_repo_path_validation_rejects_absolute(self):
        """Test that absolute repo_path is rejected."""
        with pytest.raises(ValidationError, match='must be relative'):
            MarketplaceRegistration(
                name='test',
                source='github:owner/repo',
                repo_path='/absolute/path',
            )

    def test_repo_path_validation_rejects_traversal(self):
        """Test that parent directory traversal is rejected."""
        with pytest.raises(ValidationError, match="cannot contain '..'"):
            MarketplaceRegistration(
                name='test',
                source='github:owner/repo',
                repo_path='../escape/path',
            )

    def test_serialization(self):
        """Test that MarketplaceRegistration serializes correctly."""
        reg = MarketplaceRegistration(
            name='test',
            source='github:owner/repo',
            ref='main',
            repo_path='plugins',
            auto_load='all',
        )
        data = reg.model_dump()
        assert data == {
            'name': 'test',
            'source': 'github:owner/repo',
            'ref': 'main',
            'repo_path': 'plugins',
            'auto_load': 'all',
        }


# --- Tests for Settings.registered_marketplaces ---


class TestSettingsRegisteredMarketplaces:
    """Tests for registered_marketplaces field in Settings."""

    def test_settings_default_empty_registered_marketplaces(self):
        """Test that Settings defaults to empty registered_marketplaces."""
        settings = Settings()
        assert settings.registered_marketplaces == []

    def test_settings_with_registered_marketplaces(self):
        """Test Settings with registered_marketplaces configured."""
        marketplaces = [
            MarketplaceRegistration(
                name='public',
                source='github:OpenHands/skills',
                auto_load='all',
            ),
            MarketplaceRegistration(
                name='team',
                source='github:acme/plugins',
            ),
        ]
        settings = Settings(registered_marketplaces=marketplaces)

        assert len(settings.registered_marketplaces) == 2
        assert settings.registered_marketplaces[0].name == 'public'
        assert settings.registered_marketplaces[0].auto_load == 'all'
        assert settings.registered_marketplaces[1].name == 'team'
        assert settings.registered_marketplaces[1].auto_load is None

    def test_settings_serialization_with_registered_marketplaces(self):
        """Test Settings serialization includes registered_marketplaces."""
        marketplaces = [
            MarketplaceRegistration(
                name='test',
                source='github:owner/repo',
                auto_load='all',
            ),
        ]
        settings = Settings(registered_marketplaces=marketplaces)
        data = settings.model_dump()

        assert 'registered_marketplaces' in data
        assert len(data['registered_marketplaces']) == 1
        assert data['registered_marketplaces'][0]['name'] == 'test'
        assert data['registered_marketplaces'][0]['auto_load'] == 'all'

    def test_settings_from_dict_with_registered_marketplaces(self):
        """Test creating Settings from dict with registered_marketplaces."""
        data = {
            'registered_marketplaces': [
                {
                    'name': 'custom',
                    'source': 'github:custom/repo',
                    'ref': 'v1.0.0',
                    'auto_load': 'all',
                }
            ]
        }
        settings = Settings.model_validate(data)

        assert len(settings.registered_marketplaces) == 1
        assert settings.registered_marketplaces[0].name == 'custom'
        assert settings.registered_marketplaces[0].ref == 'v1.0.0'
