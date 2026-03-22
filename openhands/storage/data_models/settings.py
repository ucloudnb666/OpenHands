from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    SerializationInfo,
    field_serializer,
    model_validator,
)

from openhands.core.config.llm_config import LLMConfig
from openhands.core.config.mcp_config import MCPConfig
from openhands.core.config.utils import load_openhands_config
from openhands.sdk.settings import AgentSettings
from openhands.storage.data_models.secrets import Secrets


def _assign_dotted_value(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = target
    parts = dotted_key.split('.')
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


# Maps legacy flat field names → SDK dotted keys for migration.
_LEGACY_FLAT_TO_SDK: dict[str, str] = {
    'llm_model': 'llm.model',
    'llm_api_key': 'llm.api_key',
    'llm_base_url': 'llm.base_url',
    'agent': 'agent',
    'confirmation_mode': 'verification.confirmation_mode',
    'security_analyzer': 'verification.security_analyzer',
    'enable_default_condenser': 'condenser.enabled',
    'condenser_max_size': 'condenser.max_size',
    'max_iterations': 'max_iterations',
}


@lru_cache(maxsize=1)
def _sdk_schema_field_metadata() -> tuple[set[str], set[str]]:
    schema = AgentSettings.export_schema()
    field_keys: set[str] = set()
    secret_keys: set[str] = set()
    for section in schema.sections:
        for field in section.fields:
            field_keys.add(field.key)
            if field.secret:
                secret_keys.add(field.key)
    return field_keys, secret_keys


def _lookup_dotted_value(source: dict[str, Any], dotted_key: str) -> Any:
    current: Any = source
    for part in dotted_key.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _normalize_persisted_sdk_value(dotted_key: str, value: Any) -> Any:
    if dotted_key == 'llm.model' and isinstance(value, str):
        if value.startswith('openhands/'):
            return value
        if value.startswith('litellm_proxy/'):
            return f'openhands/{value.removeprefix("litellm_proxy/")}'
    return value


class SandboxGroupingStrategy(str, Enum):
    """Strategy for grouping conversations within sandboxes."""

    NO_GROUPING = 'NO_GROUPING'
    GROUP_BY_NEWEST = 'GROUP_BY_NEWEST'
    LEAST_RECENTLY_USED = 'LEAST_RECENTLY_USED'
    FEWEST_CONVERSATIONS = 'FEWEST_CONVERSATIONS'
    ADD_TO_ANY = 'ADD_TO_ANY'


class Settings(BaseModel):
    """Persisted settings for OpenHands sessions.

    SDK-managed fields (LLM config, condenser, verification, agent) live
    exclusively in ``agent_settings`` using dotted keys such as
    ``llm.model``. Convenience properties provide typed access while
    preserving backward-compatible assignment semantics for legacy code.
    """

    language: str | None = None
    user_version: int | None = None
    remote_runtime_resource_factor: int | None = None
    secrets_store: Annotated[Secrets, Field(frozen=True)] = Field(
        default_factory=Secrets
    )
    enable_sound_notifications: bool = False
    enable_proactive_conversation_starters: bool = True
    enable_solvability_analysis: bool = True
    user_consents_to_analytics: bool | None = None
    sandbox_base_container_image: str | None = None
    sandbox_runtime_container_image: str | None = None
    mcp_config: MCPConfig | None = None
    search_api_key: SecretStr | None = None
    sandbox_api_key: SecretStr | None = None
    max_budget_per_task: float | None = None
    email: str | None = None
    email_verified: bool | None = None
    git_user_name: str | None = None
    git_user_email: str | None = None
    v1_enabled: bool = True
    agent_settings: dict[str, Any] = Field(default_factory=dict)
    sandbox_grouping_strategy: SandboxGroupingStrategy = (
        SandboxGroupingStrategy.NO_GROUPING
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )

    def _set_agent_setting(self, key: str, value: Any) -> None:
        if value is None:
            self.agent_settings.pop(key, None)
            return
        if isinstance(value, SecretStr):
            self.agent_settings[key] = value.get_secret_value()
            return
        self.agent_settings[key] = value

    # ------------------------------------------------------------------
    # Convenience accessors into agent_settings
    # ------------------------------------------------------------------

    @property
    def llm_model(self) -> str | None:
        return self.agent_settings.get('llm.model')

    @llm_model.setter
    def llm_model(self, value: str | None) -> None:
        self._set_agent_setting('llm.model', value)

    @property
    def llm_api_key(self) -> SecretStr | None:
        val = self.agent_settings.get('llm.api_key')
        return SecretStr(val) if val else None

    @llm_api_key.setter
    def llm_api_key(self, value: SecretStr | str | None) -> None:
        self._set_agent_setting('llm.api_key', value)

    @property
    def llm_base_url(self) -> str | None:
        return self.agent_settings.get('llm.base_url')

    @llm_base_url.setter
    def llm_base_url(self, value: str | None) -> None:
        self._set_agent_setting('llm.base_url', value)

    @property
    def agent(self) -> str | None:
        return self.agent_settings.get('agent')

    @agent.setter
    def agent(self, value: str | None) -> None:
        self._set_agent_setting('agent', value)

    @property
    def confirmation_mode(self) -> bool | None:
        return self.agent_settings.get('verification.confirmation_mode')

    @confirmation_mode.setter
    def confirmation_mode(self, value: bool | None) -> None:
        self._set_agent_setting('verification.confirmation_mode', value)

    @property
    def security_analyzer(self) -> str | None:
        return self.agent_settings.get('verification.security_analyzer')

    @security_analyzer.setter
    def security_analyzer(self, value: str | None) -> None:
        self._set_agent_setting('verification.security_analyzer', value)

    @property
    def max_iterations(self) -> int | None:
        return self.agent_settings.get('max_iterations')

    @max_iterations.setter
    def max_iterations(self, value: int | None) -> None:
        self._set_agent_setting('max_iterations', value)

    @property
    def enable_default_condenser(self) -> bool:
        return self.agent_settings.get('condenser.enabled', True)

    @enable_default_condenser.setter
    def enable_default_condenser(self, value: bool | None) -> None:
        self._set_agent_setting('condenser.enabled', value)

    @property
    def condenser_max_size(self) -> int | None:
        return self.agent_settings.get('condenser.max_size')

    @condenser_max_size.setter
    def condenser_max_size(self, value: int | None) -> None:
        self._set_agent_setting('condenser.max_size', value)

    @property
    def llm_api_key_is_set(self) -> bool:
        val = self.agent_settings.get('llm.api_key')
        return bool(val and str(val).strip())

    def normalized_agent_settings(
        self, *, strip_secret_values: bool = False
    ) -> dict[str, Any]:
        """Return a canonical flat agent_settings mapping for persistence.

        This normalizes schema/version drift without running values back through
        runtime-only SDK coercions such as the internal OpenHands LLM provider
        rewrite.
        """
        payload: dict[str, Any] = {}
        for key, value in self.agent_settings.items():
            if key == 'schema_version':
                payload['schema_version'] = value
                continue
            _assign_dotted_value(payload, key, value)

        try:
            migrated_payload = AgentSettings._migrate_schema(dict(payload))
            if not isinstance(migrated_payload, dict):
                return dict(self.agent_settings)
        except Exception:
            return dict(self.agent_settings)

        field_keys, secret_keys = _sdk_schema_field_metadata()
        extras = {
            key: value
            for key, value in self.agent_settings.items()
            if key not in field_keys and key != 'schema_version'
        }
        normalized = dict(extras)
        normalized['schema_version'] = migrated_payload.get('schema_version', 1)

        for key in field_keys:
            value = _lookup_dotted_value(migrated_payload, key)
            if value is None:
                continue
            if strip_secret_values and key in secret_keys:
                continue
            normalized[key] = _normalize_persisted_sdk_value(key, value)

        return normalized

    def normalize_agent_settings(self, *, strip_secret_values: bool = False) -> bool:
        normalized = self.normalized_agent_settings(
            strip_secret_values=strip_secret_values
        )
        if normalized == self.agent_settings:
            return False
        object.__setattr__(self, 'agent_settings', normalized)
        return True

    @property
    def sdk_settings_values(self) -> dict[str, Any]:
        return self.agent_settings

    @sdk_settings_values.setter
    def sdk_settings_values(self, value: dict[str, Any] | None) -> None:
        self.agent_settings = dict(value or {})

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @field_serializer('search_api_key')
    def api_key_serializer(self, api_key: SecretStr | None, info: SerializationInfo):
        if api_key is None:
            return None
        secret_value = api_key.get_secret_value()
        if not secret_value or not secret_value.strip():
            return None
        context = info.context
        if context and context.get('expose_secrets', False):
            return secret_value
        return str(api_key)

    @field_serializer('agent_settings')
    def agent_settings_field_serializer(
        self, values: dict[str, Any], info: SerializationInfo
    ) -> dict[str, Any]:
        """Expose secret SDK values only when ``expose_secrets`` is set."""
        context = info.context
        if context and context.get('expose_secrets', False):
            return values
        # Redact — caller should use _extract_agent_settings for GET.
        return {k: v for k, v in values.items()}

    @model_validator(mode='before')
    @classmethod
    def _migrate_legacy_fields(cls, data: dict | object) -> dict | object:
        """Migrate legacy flat fields into ``agent_settings``."""
        if not isinstance(data, dict):
            return data

        agent_vals: dict[str, Any] = dict(data.get('agent_settings') or {})

        legacy_agent_vals = data.pop('sdk_settings_values', None)
        if isinstance(legacy_agent_vals, dict):
            for key, value in legacy_agent_vals.items():
                agent_vals.setdefault(key, value)

        for flat_key, dotted_key in _LEGACY_FLAT_TO_SDK.items():
            if flat_key in data and dotted_key not in agent_vals:
                value = data[flat_key]
                if value is not None:
                    # Unwrap SecretStr / pydantic masked strings
                    if isinstance(value, SecretStr):
                        value = value.get_secret_value()
                    elif isinstance(value, str) and value.startswith('**'):
                        continue  # skip masked values
                    agent_vals[dotted_key] = value

        # Remove legacy flat fields so Pydantic doesn't complain
        for flat_key in _LEGACY_FLAT_TO_SDK:
            data.pop(flat_key, None)

        data['agent_settings'] = agent_vals

        # Handle legacy secrets_store
        secrets_store = data.get('secrets_store')
        if isinstance(secrets_store, dict):
            custom_secrets = secrets_store.get('custom_secrets')
            tokens = secrets_store.get('provider_tokens')
            secret_store = Secrets(provider_tokens={}, custom_secrets={})  # type: ignore[arg-type]
            if isinstance(tokens, dict):
                converted_store = Secrets(provider_tokens=tokens)  # type: ignore[arg-type]
                secret_store = secret_store.model_copy(
                    update={'provider_tokens': converted_store.provider_tokens}
                )
            if isinstance(custom_secrets, dict):
                converted_store = Secrets(custom_secrets=custom_secrets)  # type: ignore[arg-type]
                secret_store = secret_store.model_copy(
                    update={'custom_secrets': converted_store.custom_secrets}
                )
            data['secret_store'] = secret_store

        return data

    @model_validator(mode='after')
    def _normalize_agent_settings_after(self) -> 'Settings':
        self.normalize_agent_settings()
        return self

    @field_serializer('secrets_store')
    def secrets_store_serializer(self, secrets: Secrets, info: SerializationInfo):
        return {'provider_tokens': {}}

    # ------------------------------------------------------------------
    # Factory / conversion
    # ------------------------------------------------------------------

    @staticmethod
    def from_config() -> Settings | None:
        app_config = load_openhands_config()
        llm_config: LLMConfig = app_config.get_llm_config()
        if llm_config.api_key is None:
            return None
        security = app_config.security

        mcp_config = None
        if hasattr(app_config, 'mcp'):
            mcp_config = app_config.mcp

        raw_api_key = llm_config.api_key.get_secret_value()

        agent_vals: dict[str, Any] = {
            'agent': app_config.default_agent,
            'llm.model': llm_config.model,
            'llm.api_key': raw_api_key,
            'llm.base_url': llm_config.base_url,
            'verification.confirmation_mode': security.confirmation_mode,
            'verification.security_analyzer': security.security_analyzer,
            'max_iterations': app_config.max_iterations,
        }

        return Settings(
            language='en',
            remote_runtime_resource_factor=app_config.sandbox.remote_runtime_resource_factor,
            mcp_config=mcp_config,
            search_api_key=app_config.search_api_key,
            max_budget_per_task=app_config.max_budget_per_task,
            agent_settings={k: v for k, v in agent_vals.items() if v is not None},
        )

    def merge_with_config_settings(self) -> 'Settings':
        """Merge config.toml MCP settings with stored settings."""
        config_settings = Settings.from_config()
        if not config_settings or not config_settings.mcp_config:
            return self
        if not self.mcp_config:
            self.mcp_config = config_settings.mcp_config
            return self
        merged_mcp = MCPConfig(
            sse_servers=list(config_settings.mcp_config.sse_servers)
            + list(self.mcp_config.sse_servers),
            stdio_servers=list(config_settings.mcp_config.stdio_servers)
            + list(self.mcp_config.stdio_servers),
            shttp_servers=list(config_settings.mcp_config.shttp_servers)
            + list(self.mcp_config.shttp_servers),
        )
        self.mcp_config = merged_mcp
        return self

    def to_agent_settings(self) -> AgentSettings:
        """Build SDK ``AgentSettings`` from persisted ``agent_settings``."""
        payload: dict[str, Any] = {}
        for key, value in self.agent_settings.items():
            _assign_dotted_value(payload, key, value)
        return AgentSettings.model_validate(payload)
