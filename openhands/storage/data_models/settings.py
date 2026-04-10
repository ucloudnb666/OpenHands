from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Annotated, Any

from fastmcp.mcp_config import MCPConfig as SDKMCPConfig
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    SerializationInfo,
    field_serializer,
    model_validator,
)

from openhands.core.config.llm_config import LLMConfig
from openhands.core.config.mcp_config import MCPConfig as LegacyMCPConfig
from openhands.core.config.utils import load_openhands_config
from openhands.sdk.settings import AgentSettings, ConversationSettings
from openhands.storage.data_models.secrets import Secrets


def _assign_dotted_value(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = target
    parts = dotted_key.split('.')
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


# Maps legacy flat field names → SDK keys for migration.
_LEGACY_FLAT_TO_SDK: dict[str, str] = {
    'agent': 'agent',
    'llm_model': 'llm.model',
    'llm_api_key': 'llm.api_key',
    'llm_base_url': 'llm.base_url',
    'mcp_config': 'mcp_config',
    'enable_default_condenser': 'condenser.enabled',
    'condenser_max_size': 'condenser.max_size',
}

_CONVERSATION_SETTINGS_FIELD_MAP: dict[str, str] = {
    'max_iterations': 'max_iterations',
    'verification.confirmation_mode': 'confirmation_mode',
    'verification.security_analyzer': 'security_analyzer',
}

_CONVERSATION_SETTINGS_REVERSE_FIELD_MAP: dict[str, str] = {
    value: key for key, value in _CONVERSATION_SETTINGS_FIELD_MAP.items()
}


@lru_cache(maxsize=1)
def _conversation_schema_field_keys() -> set[str]:
    schema = ConversationSettings.export_schema()
    return {field.key for section in schema.sections for field in section.fields}


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


@lru_cache(maxsize=1)
def _sdk_schema_top_level_keys() -> set[str]:
    field_keys, _ = _sdk_schema_field_metadata()
    return {'schema_version'} | {key.split('.')[0] for key in field_keys}


def _lookup_dotted_value(
    source: dict[str, Any], dotted_key: str, default: Any = None
) -> Any:
    current: Any = source
    for part in dotted_key.split('.'):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _remove_dotted_value(target: dict[str, Any], dotted_key: str) -> None:
    parents: list[tuple[dict[str, Any], str]] = []
    current: Any = target
    for part in dotted_key.split('.')[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        parents.append((current, part))
        current = current[part]

    if not isinstance(current, dict):
        return

    current.pop(dotted_key.split('.')[-1], None)
    while parents:
        parent, part = parents.pop()
        child = parent.get(part)
        if isinstance(child, dict) and not child:
            parent.pop(part, None)


def _normalize_persisted_sdk_value(dotted_key: str, value: Any) -> Any:
    normalized_value = _coerce_agent_setting_value(value)
    if dotted_key == 'llm.model' and isinstance(normalized_value, str):
        if normalized_value.startswith('openhands/'):
            return normalized_value
        if normalized_value.startswith('litellm_proxy/'):
            return f'openhands/{normalized_value.removeprefix("litellm_proxy/")}'
    return normalized_value


def _coerce_agent_setting_value(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, SDKMCPConfig):
        return value.model_dump(exclude_none=True, exclude_defaults=True)
    if isinstance(value, LegacyMCPConfig):
        return value.model_dump(mode='python')
    return value


def _legacy_mcp_config_to_sdk(value: LegacyMCPConfig) -> SDKMCPConfig | None:
    mcp_servers: dict[str, Any] = {}

    for index, sse_server in enumerate(value.sse_servers):
        sse_server_config: dict[str, Any] = {
            'transport': 'sse',
            'url': sse_server.url,
        }
        if sse_server.api_key:
            sse_server_config['auth'] = sse_server.api_key
        mcp_servers[f'sse_{index}'] = sse_server_config

    for index, shttp_server in enumerate(value.shttp_servers):
        shttp_server_config: dict[str, Any] = {
            'transport': 'http',
            'url': shttp_server.url,
        }
        if shttp_server.api_key:
            shttp_server_config['auth'] = shttp_server.api_key
        if shttp_server.timeout is not None:
            shttp_server_config['timeout'] = shttp_server.timeout
        mcp_servers[f'shttp_{index}'] = shttp_server_config

    for stdio_server in value.stdio_servers:
        stdio_server_config: dict[str, Any] = {'command': stdio_server.command}
        if stdio_server.args:
            stdio_server_config['args'] = list(stdio_server.args)
        if stdio_server.env:
            stdio_server_config['env'] = dict(stdio_server.env)
        mcp_servers[stdio_server.name] = stdio_server_config

    if not mcp_servers:
        return None
    return SDKMCPConfig.model_validate({'mcpServers': mcp_servers})


def _sdk_mcp_config_to_legacy(value: SDKMCPConfig) -> LegacyMCPConfig:
    raw_config = value.model_dump(exclude_none=True)
    sse_servers: list[dict[str, Any]] = []
    shttp_servers: list[dict[str, Any]] = []
    stdio_servers: list[dict[str, Any]] = []

    for server_name, server_config in raw_config.get('mcpServers', {}).items():
        url = server_config.get('url')
        if url:
            transport = server_config.get('transport')
            if transport is None:
                transport = 'sse' if '/sse' in str(url).lower() else 'http'

            legacy_server: dict[str, Any] = {'url': url}
            auth = server_config.get('auth')
            if isinstance(auth, str) and auth != 'oauth':
                legacy_server['api_key'] = auth

            if transport == 'sse':
                sse_servers.append(legacy_server)
                continue

            if server_config.get('timeout') is not None:
                legacy_server['timeout'] = server_config['timeout']
            shttp_servers.append(legacy_server)
            continue

        stdio_server: dict[str, Any] = {
            'name': server_name,
            'command': server_config['command'],
        }
        if server_config.get('args'):
            stdio_server['args'] = server_config['args']
        if server_config.get('env'):
            stdio_server['env'] = server_config['env']
        stdio_servers.append(stdio_server)

    return LegacyMCPConfig.model_validate(
        {
            'sse_servers': sse_servers,
            'shttp_servers': shttp_servers,
            'stdio_servers': stdio_servers,
        }
    )


def _sdk_mcp_config_from_value(value: Any) -> SDKMCPConfig | None:
    if value in (None, {}):
        return None
    if isinstance(value, SDKMCPConfig):
        return value if value.mcpServers else None
    if isinstance(value, LegacyMCPConfig):
        return _legacy_mcp_config_to_sdk(value)
    if isinstance(value, dict) and 'mcpServers' in value:
        if not value.get('mcpServers'):
            return None
        return SDKMCPConfig.model_validate(value)
    return _legacy_mcp_config_to_sdk(LegacyMCPConfig.model_validate(value))


def _merge_sdk_mcp_configs(
    base_config: SDKMCPConfig | None, extra_config: SDKMCPConfig | None
) -> SDKMCPConfig | None:
    if base_config is None:
        return extra_config
    if extra_config is None:
        return base_config

    merged_servers: dict[str, Any] = {}

    def _add_server(server_name: str, server_config: dict[str, Any]) -> None:
        candidate = server_name or 'server'
        if candidate not in merged_servers:
            merged_servers[candidate] = server_config
            return

        suffix = 1
        while f'{candidate}_{suffix}' in merged_servers:
            suffix += 1
        merged_servers[f'{candidate}_{suffix}'] = server_config

    for config in (base_config, extra_config):
        raw_config = _coerce_agent_setting_value(config)
        for server_name, server_config in raw_config.get('mcpServers', {}).items():
            _add_server(server_name, server_config)

    if not merged_servers:
        return None

    return SDKMCPConfig.model_validate({'mcpServers': merged_servers})


def _legacy_mcp_config_from_value(value: Any) -> LegacyMCPConfig | None:
    if value in (None, {}):
        return None
    if isinstance(value, LegacyMCPConfig):
        return value
    if isinstance(value, SDKMCPConfig):
        return _sdk_mcp_config_to_legacy(value)
    if isinstance(value, dict) and 'mcpServers' in value:
        return _sdk_mcp_config_to_legacy(SDKMCPConfig.model_validate(value))
    return LegacyMCPConfig.model_validate(value)


def _normalize_agent_setting_value(key: str, value: Any) -> Any:
    if key == 'mcp_config':
        sdk_mcp_config = _sdk_mcp_config_from_value(value)
        if sdk_mcp_config is None:
            return None
        return _coerce_agent_setting_value(sdk_mcp_config)
    return _coerce_agent_setting_value(value)


class SandboxGroupingStrategy(str, Enum):
    """Strategy for grouping conversations within sandboxes."""

    NO_GROUPING = 'NO_GROUPING'
    GROUP_BY_NEWEST = 'GROUP_BY_NEWEST'
    LEAST_RECENTLY_USED = 'LEAST_RECENTLY_USED'
    FEWEST_CONVERSATIONS = 'FEWEST_CONVERSATIONS'
    ADD_TO_ANY = 'ADD_TO_ANY'


class Settings(BaseModel):
    """Persisted settings for OpenHands sessions.

    SDK-managed fields (agent, llm, mcp, condenser, verification) live
    exclusively in ``agent_settings``. Non-agent product settings remain as
    top-level fields on this model.
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
    mcp_config: LegacyMCPConfig | None = None
    disabled_skills: list[str] | None = None
    search_api_key: SecretStr | None = None
    sandbox_api_key: SecretStr | None = None
    confirmation_mode: bool | None = None
    security_analyzer: str | None = None
    max_iterations: int | None = None
    max_budget_per_task: float | None = None
    email: str | None = None
    email_verified: bool | None = None
    git_user_name: str | None = None
    git_user_email: str | None = None
    v1_enabled: bool = True
    raw_agent_settings: dict[str, Any] = Field(
        default_factory=dict, alias='agent_settings'
    )
    raw_conversation_settings: dict[str, Any] = Field(
        default_factory=dict, alias='conversation_settings'
    )
    sandbox_grouping_strategy: SandboxGroupingStrategy = (
        SandboxGroupingStrategy.NO_GROUPING
    )

    model_config = ConfigDict(
        validate_assignment=True, populate_by_name=True, serialize_by_alias=True
    )
    _agent_settings: AgentSettings = PrivateAttr(default_factory=AgentSettings)

    @property
    def agent_settings(self) -> AgentSettings:
        return self._agent_settings

    def to_legacy_mcp_config(self) -> LegacyMCPConfig | None:
        return _legacy_mcp_config_from_value(self.agent_settings.mcp_config)

    def _reload_agent_settings(self) -> None:
        self._agent_settings = AgentSettings.from_persisted(self.raw_agent_settings)

    def _extra_agent_settings_payload(self) -> dict[str, Any]:
        field_keys, _ = _sdk_schema_field_metadata()
        top_level_keys = _sdk_schema_top_level_keys()
        extras: dict[str, Any] = {}
        for key, value in self.raw_agent_settings.items():
            if key == 'schema_version':
                continue
            if '.' in key:
                if key not in field_keys:
                    extras[key] = value
                continue
            if key not in top_level_keys:
                extras[key] = value
        return extras

    def _persisted_agent_settings_payload(
        self, *, strip_secret_values: bool = False
    ) -> dict[str, Any]:
        payload = self.agent_settings.model_dump(
            mode='json', context={'expose_secrets': True}
        )
        payload.update(self._extra_agent_settings_payload())
        if not strip_secret_values:
            return payload

        _, secret_keys = _sdk_schema_field_metadata()
        stripped_payload = dict(payload)
        for key in secret_keys:
            _remove_dotted_value(stripped_payload, key)
        return stripped_payload

    def get_agent_setting(self, key: str, default: Any = None) -> Any:
        if key == 'schema_version':
            return self.raw_agent_settings.get(key, default)
        value = (
            _lookup_dotted_value(self.raw_agent_settings, key, default)
            if '.' in key
            else self.raw_agent_settings.get(key, default)
        )
        return value

    def set_agent_setting(self, key: str, value: Any) -> None:
        normalized_value = _normalize_agent_setting_value(key, value)
        field_keys, _ = _sdk_schema_field_metadata()
        if key == 'schema_version' or key not in field_keys:
            updated = dict(self.raw_agent_settings)
            if normalized_value is None:
                updated.pop(key, None)
            else:
                updated[key] = normalized_value
            object.__setattr__(self, 'raw_agent_settings', updated)
            self.normalize_agent_settings()
            return

        self._agent_settings = self.agent_settings.patch({key: normalized_value})
        object.__setattr__(
            self,
            'raw_agent_settings',
            self._persisted_agent_settings_payload(),
        )

    def get_secret_agent_setting(self, key: str) -> SecretStr | None:
        value = self.get_agent_setting(key)
        if not value:
            return None
        return SecretStr(str(value))

    def conversation_settings_values(self) -> dict[str, Any]:
        values = {
            key: value
            for key, value in self.raw_conversation_settings.items()
            if key != 'schema_version' and key not in _conversation_schema_field_keys()
        }
        values['schema_version'] = ConversationSettings.CURRENT_PERSISTED_VERSION
        for key, field_name in _CONVERSATION_SETTINGS_FIELD_MAP.items():
            value = getattr(self, field_name)
            if value is not None:
                values[key] = value
        return values

    def get_conversation_setting(self, key: str, default: Any = None) -> Any:
        field_name = _CONVERSATION_SETTINGS_FIELD_MAP.get(key)
        if field_name is not None:
            value = getattr(self, field_name)
            return default if value is None else value
        return self.raw_conversation_settings.get(key, default)

    def set_conversation_setting(self, key: str, value: Any) -> None:
        field_name = _CONVERSATION_SETTINGS_FIELD_MAP.get(key)
        if field_name is not None:
            setattr(self, field_name, value)
            return

        updated = dict(self.raw_conversation_settings)
        if value is None:
            updated.pop(key, None)
        else:
            updated[key] = value
        object.__setattr__(self, 'raw_conversation_settings', updated)

    @property
    def agent(self) -> str | None:
        value = self.get_agent_setting('agent')
        return str(value) if value is not None else None

    @agent.setter
    def agent(self, value: str | None) -> None:
        self.set_agent_setting('agent', value)

    @property
    def llm_model(self) -> str | None:
        value = self.get_agent_setting('llm.model')
        return str(value) if value is not None else None

    @llm_model.setter
    def llm_model(self, value: str | None) -> None:
        self.set_agent_setting('llm.model', value)

    @property
    def llm_base_url(self) -> str | None:
        value = self.get_agent_setting('llm.base_url')
        return str(value) if value is not None else None

    @llm_base_url.setter
    def llm_base_url(self, value: str | None) -> None:
        self.set_agent_setting('llm.base_url', value)

    @property
    def llm_api_key(self) -> SecretStr | None:
        return self.get_secret_agent_setting('llm.api_key')

    @llm_api_key.setter
    def llm_api_key(self, value: SecretStr | str | None) -> None:
        normalized_value = (
            value.get_secret_value() if isinstance(value, SecretStr) else value
        )
        self.set_agent_setting('llm.api_key', normalized_value)

    @property
    def enable_default_condenser(self) -> bool | None:
        value = self.get_agent_setting('condenser.enabled')
        return bool(value) if value is not None else None

    @enable_default_condenser.setter
    def enable_default_condenser(self, value: bool | None) -> None:
        self.set_agent_setting('condenser.enabled', value)

    @property
    def condenser_max_size(self) -> int | None:
        value = self.get_agent_setting('condenser.max_size')
        return int(value) if value is not None else None

    @condenser_max_size.setter
    def condenser_max_size(self, value: int | None) -> None:
        self.set_agent_setting('condenser.max_size', value)

    @property
    def llm_api_key_is_set(self) -> bool:
        val = self.get_secret_agent_setting('llm.api_key')
        return bool(val and val.get_secret_value().strip())

    def agent_settings_values(
        self, *, strip_secret_values: bool = False
    ) -> dict[str, Any]:
        field_keys, secret_keys = _sdk_schema_field_metadata()
        payload = self.normalized_agent_settings(
            strip_secret_values=strip_secret_values
        )
        values = {
            key: value for key, value in self._extra_agent_settings_payload().items()
        }
        values['schema_version'] = payload.get(
            'schema_version', AgentSettings.CURRENT_PERSISTED_VERSION
        )

        missing = object()
        for key in field_keys:
            if strip_secret_values and key in secret_keys:
                continue
            value = _lookup_dotted_value(payload, key, missing)
            if value is missing:
                continue
            values[key] = _normalize_persisted_sdk_value(key, value)

        return values

    def normalized_agent_settings(
        self, *, strip_secret_values: bool = False
    ) -> dict[str, Any]:
        """Return the canonical nested agent_settings mapping for persistence."""
        return self._persisted_agent_settings_payload(
            strip_secret_values=strip_secret_values
        )

    def normalize_agent_settings(self, *, strip_secret_values: bool = False) -> bool:
        self._reload_agent_settings()
        normalized = self.normalized_agent_settings(
            strip_secret_values=strip_secret_values
        )
        changed = normalized != self.raw_agent_settings
        if changed:
            object.__setattr__(self, 'raw_agent_settings', normalized)
        return changed

    @field_serializer('raw_conversation_settings')
    def raw_conversation_settings_field_serializer(
        self, values: dict[str, Any], info: SerializationInfo
    ) -> dict[str, Any]:
        return self.conversation_settings_values()

    def legacy_conversation_settings_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.confirmation_mode is not None:
            payload['verification.confirmation_mode'] = self.confirmation_mode
        if self.security_analyzer is not None:
            payload['verification.security_analyzer'] = self.security_analyzer
        if self.max_iterations is not None:
            payload['max_iterations'] = self.max_iterations
        return payload

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

    @field_serializer('raw_agent_settings')
    def raw_agent_settings_field_serializer(
        self, values: dict[str, Any], info: SerializationInfo
    ) -> dict[str, Any]:
        """Serialize agent_settings as flattened API data or nested persisted data."""
        context = info.context or {}
        if context.get('persist_settings', False):
            return self.normalized_agent_settings(
                strip_secret_values=context.get('strip_secret_values', False)
            )

        serialized = self.agent_settings_values(strip_secret_values=False)
        if context.get('expose_secrets', False):
            return serialized

        _, secret_keys = _sdk_schema_field_metadata()
        for key in secret_keys:
            value = serialized.get(key)
            if value and value != '<hidden>':
                serialized[key] = str(SecretStr(str(value)))
        return serialized

    @model_validator(mode='before')
    @classmethod
    def _migrate_legacy_fields(cls, data: dict | object) -> dict | object:
        """Migrate legacy flat fields into ``agent_settings``."""
        if not isinstance(data, dict):
            return data

        raw_agent_settings = data.pop('raw_agent_settings', None)
        agent_settings = data.pop('agent_settings', None)
        agent_vals: dict[str, Any] = dict(raw_agent_settings or agent_settings or {})
        if 'mcp_config' in agent_vals:
            agent_vals['mcp_config'] = _normalize_agent_setting_value(
                'mcp_config', agent_vals['mcp_config']
            )

        for legacy_key in ('sdk_settings_values', 'mcp_config'):
            legacy_agent_vals = data.pop(legacy_key, None)
            if legacy_key == 'sdk_settings_values' and isinstance(
                legacy_agent_vals, dict
            ):
                for key, value in legacy_agent_vals.items():
                    agent_vals.setdefault(
                        key, _normalize_agent_setting_value(key, value)
                    )
            elif legacy_key == 'mcp_config' and legacy_agent_vals is not None:
                agent_vals.setdefault(
                    'mcp_config',
                    _normalize_agent_setting_value('mcp_config', legacy_agent_vals),
                )

        for flat_key, sdk_key in _LEGACY_FLAT_TO_SDK.items():
            if flat_key in data and sdk_key not in agent_vals:
                value = data[flat_key]
                if value is not None:
                    if isinstance(value, str) and value.startswith('**'):
                        continue
                    agent_vals[sdk_key] = _normalize_agent_setting_value(sdk_key, value)

        raw_conversation_settings = data.pop('raw_conversation_settings', None)
        conversation_settings = data.pop('conversation_settings', None)
        conversation_vals: dict[str, Any] = dict(
            raw_conversation_settings or conversation_settings or {}
        )

        missing = object()
        for (
            field_name,
            conversation_key,
        ) in _CONVERSATION_SETTINGS_REVERSE_FIELD_MAP.items():
            conversation_value = conversation_vals.get(conversation_key, missing)
            if conversation_value is not missing and data.get(field_name) is None:
                data[field_name] = conversation_value

            legacy_value = (
                _lookup_dotted_value(agent_vals, conversation_key, missing)
                if '.' in conversation_key
                else agent_vals.get(conversation_key, missing)
            )
            if legacy_value is not missing and data.get(field_name) is None:
                data[field_name] = legacy_value
            if '.' in conversation_key:
                _remove_dotted_value(agent_vals, conversation_key)
            else:
                agent_vals.pop(conversation_key, None)

        for flat_key in _LEGACY_FLAT_TO_SDK:
            data.pop(flat_key, None)

        data['raw_agent_settings'] = agent_vals
        data['raw_conversation_settings'] = conversation_vals

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
        object.__setattr__(
            self, 'raw_conversation_settings', self.conversation_settings_values()
        )
        return self

    @field_serializer('secrets_store')
    def secrets_store_serializer(self, secrets: Secrets, info: SerializationInfo):
        return {'provider_tokens': {}}

    @staticmethod
    def from_config() -> Settings | None:
        app_config = load_openhands_config()
        llm_config: LLMConfig = app_config.get_llm_config()
        if llm_config.api_key is None:
            return None

        settings = Settings(
            language='en',
            remote_runtime_resource_factor=app_config.sandbox.remote_runtime_resource_factor,
            search_api_key=app_config.search_api_key,
            max_budget_per_task=app_config.max_budget_per_task,
        )
        settings.set_agent_setting('agent', app_config.default_agent)
        settings.set_agent_setting('llm.model', llm_config.model)
        settings.set_agent_setting('llm.api_key', llm_config.api_key)
        settings.set_agent_setting('llm.base_url', llm_config.base_url)
        settings.confirmation_mode = app_config.security.confirmation_mode
        settings.security_analyzer = app_config.security.security_analyzer
        settings.max_iterations = app_config.max_iterations
        if hasattr(app_config, 'mcp'):
            settings.set_agent_setting('mcp_config', app_config.mcp)
        return settings

    def merge_with_config_settings(self) -> 'Settings':
        """Merge config.toml MCP settings with stored SDK agent_settings."""
        config_settings = Settings.from_config()
        if not config_settings:
            return self

        merged_mcp = _merge_sdk_mcp_configs(
            _sdk_mcp_config_from_value(
                config_settings.raw_agent_settings.get('mcp_config')
            ),
            _sdk_mcp_config_from_value(self.raw_agent_settings.get('mcp_config')),
        )
        if merged_mcp is None:
            return self

        self.raw_agent_settings['mcp_config'] = _coerce_agent_setting_value(merged_mcp)
        self.normalize_agent_settings()
        return self

    def to_agent_settings(self) -> AgentSettings:
        """Return the cached SDK ``AgentSettings`` model."""
        return self.agent_settings
