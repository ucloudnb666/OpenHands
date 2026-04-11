from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Annotated, Any

from fastmcp.mcp_config import MCPConfig as SDKMCPConfig
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
from openhands.core.config.utils import load_openhands_config
from openhands.sdk.settings import AgentSettings, ConversationSettings
from openhands.storage.data_models.secrets import Secrets
from openhands.utils.jsonpatch_compat import deep_merge


# Maps legacy flat field names → nested SDK dict paths for migration.
_LEGACY_FLAT_TO_SDK: dict[str, list[str]] = {
    "agent": ["agent"],
    "llm_model": ["llm", "model"],
    "llm_api_key": ["llm", "api_key"],
    "llm_base_url": ["llm", "base_url"],
    "mcp_config": ["mcp_config"],
    "enable_default_condenser": ["condenser", "enabled"],
    "condenser_max_size": ["condenser", "max_size"],
}

_CONVERSATION_SETTINGS_KEYS = frozenset(
    f.key for s in ConversationSettings.export_schema().sections for f in s.fields
)


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


def _coerce_value(value: Any) -> Any:
    """Unwrap SecretStr to plain values."""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, SDKMCPConfig):
        return value.model_dump(exclude_none=True, exclude_defaults=True) or None
    return value


def _normalize_mcp_value(value: Any) -> Any:
    """Normalize an MCP config value to SDK dict format."""
    sdk = _sdk_mcp_config_from_value(value)
    if sdk is None:
        return None
    return sdk.model_dump(exclude_none=True, exclude_defaults=True)


def _set_nested(target: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a value in a nested dict given a path like ['llm', 'model']."""
    current = target
    for part in path[:-1]:
        current = current.setdefault(part, {})
    current[path[-1]] = value


def _lookup_dotted(source: dict[str, Any], dotted_key: str) -> Any:
    """Lookup a value in a nested dict using a dotted key like 'llm.model'."""
    current: Any = source
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _normalize_model_name(key: str, value: Any) -> Any:
    """Normalize litellm_proxy/ prefix → openhands/ for model names."""
    if key == "llm.model" and isinstance(value, str):
        if value.startswith("litellm_proxy/"):
            return f"openhands/{value.removeprefix('litellm_proxy/')}"
    return value


def _sdk_mcp_config_from_value(value: Any) -> SDKMCPConfig | None:
    """Convert various MCP config representations to SDKMCPConfig.

    Handles: SDKMCPConfig instances, dicts with 'mcpServers', and legacy
    dicts with 'sse_servers'/'shttp_servers'/'stdio_servers'.
    """
    if value in (None, {}):
        return None
    if isinstance(value, SDKMCPConfig):
        return value if value.mcpServers else None
    if isinstance(value, dict):
        if 'mcpServers' in value:
            if not value.get('mcpServers'):
                return None
            return SDKMCPConfig.model_validate(value)
        # Legacy dict format with sse_servers/shttp_servers/stdio_servers
        from openhands.core.config.mcp_config import mcp_config_from_toml

        result = mcp_config_from_toml(value)
        cfg = result.get('mcp')
        return cfg if cfg and cfg.mcpServers else None
    return None


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
        raw_config = config.model_dump(exclude_none=True)
        for server_name, server_config in raw_config.get('mcpServers', {}).items():
            _add_server(server_name, server_config)

    if not merged_servers:
        return None

    return SDKMCPConfig.model_validate({'mcpServers': merged_servers})


class SandboxGroupingStrategy(str, Enum):
    """Strategy for grouping conversations within sandboxes."""

    NO_GROUPING = 'NO_GROUPING'
    GROUP_BY_NEWEST = 'GROUP_BY_NEWEST'
    LEAST_RECENTLY_USED = 'LEAST_RECENTLY_USED'
    FEWEST_CONVERSATIONS = 'FEWEST_CONVERSATIONS'
    ADD_TO_ANY = 'ADD_TO_ANY'


_SETTINGS_FROZEN_FIELDS = frozenset(["secrets_store"])


class Settings(BaseModel):
    """Persisted settings for OpenHands sessions.

    Agent settings (agent, llm, mcp, condenser) live in ``agent_settings``.
    Conversation settings (max_iterations, confirmation_mode, security_analyzer)
    live in ``conversation_settings``.
    Product settings remain as top-level fields.
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
    disabled_skills: list[str] | None = None
    search_api_key: SecretStr | None = None
    sandbox_api_key: SecretStr | None = None
    max_budget_per_task: float | None = None
    email: str | None = None
    email_verified: bool | None = None
    git_user_name: str | None = None
    git_user_email: str | None = None
    v1_enabled: bool = True
    agent_settings: AgentSettings = Field(default_factory=AgentSettings)
    conversation_settings: ConversationSettings = Field(
        default_factory=ConversationSettings
    )
    sandbox_grouping_strategy: SandboxGroupingStrategy = (
        SandboxGroupingStrategy.NO_GROUPING
    )

    model_config = ConfigDict(populate_by_name=True)

    # ── Convenience properties (backward-compat shims) ──────────────

    @property
    def llm_model(self) -> str | None:
        return self.agent_settings.llm.model

    @llm_model.setter
    def llm_model(self, value: str | None) -> None:
        if value is not None:
            self.agent_settings.llm.model = value

    @property
    def llm_base_url(self) -> str | None:
        return self.agent_settings.llm.base_url

    @llm_base_url.setter
    def llm_base_url(self, value: str | None) -> None:
        self.agent_settings.llm.base_url = value

    @property
    def llm_api_key(self) -> SecretStr | None:
        raw = self.agent_settings.llm.api_key
        if raw is None:
            return None
        secret_value = (
            raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)
        )
        return SecretStr(secret_value) if secret_value else None

    @llm_api_key.setter
    def llm_api_key(self, value: SecretStr | str | None) -> None:
        if isinstance(value, SecretStr):
            self.agent_settings.llm.api_key = value
        elif value is not None:
            self.agent_settings.llm.api_key = SecretStr(value)
        else:
            self.agent_settings.llm.api_key = None

    @property
    def llm_api_key_is_set(self) -> bool:
        raw = self.agent_settings.llm.api_key
        if raw is None:
            return False
        secret_value = (
            raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)
        )
        return bool(secret_value and secret_value.strip())

    @property
    def agent(self) -> str | None:
        return self.agent_settings.agent

    @agent.setter
    def agent(self, value: str | None) -> None:
        if value is not None:
            self.agent_settings.agent = value

    @property
    def enable_default_condenser(self) -> bool | None:
        return self.agent_settings.condenser.enabled

    @enable_default_condenser.setter
    def enable_default_condenser(self, value: bool | None) -> None:
        if value is not None:
            self.agent_settings.condenser.enabled = value

    @property
    def condenser_max_size(self) -> int | None:
        return self.agent_settings.condenser.max_size

    @condenser_max_size.setter
    def condenser_max_size(self, value: int | None) -> None:
        if value is not None:
            self.agent_settings.condenser.max_size = value

    # ── Batch update ────────────────────────────────────────────────

    def update(self, payload: dict[str, Any]) -> None:
        """Apply a batch of changes from a nested dict.

        ``agent_settings`` values use nested dict shape (matching model_dump).
        ``conversation_settings`` values likewise.
        Top-level keys are set directly on the model.
        """
        if "agent_settings" in payload:
            agent_update = payload["agent_settings"]
            if isinstance(agent_update, dict):
                coerced: dict[str, Any] = {}
                for key, value in agent_update.items():
                    coerced[key] = (
                        _coerce_value(value) if not isinstance(value, dict) else value
                    )
                merged = deep_merge(
                    self.agent_settings.model_dump(
                        mode="json", context={"expose_secrets": True}
                    ),
                    coerced,
                )
                # Use object.__setattr__ to avoid validate_assignment
                # side-effects on other fields.
                object.__setattr__(
                    self, "agent_settings", AgentSettings.model_validate(merged)
                )

        if "conversation_settings" in payload:
            conv_update = payload["conversation_settings"]
            if isinstance(conv_update, dict):
                merged = deep_merge(
                    self.conversation_settings.model_dump(mode="json"),
                    conv_update,
                )
                object.__setattr__(
                    self,
                    "conversation_settings",
                    ConversationSettings.model_validate(merged),
                )

        for key, value in payload.items():
            if key in ("agent_settings", "conversation_settings"):
                continue
            if key in Settings.model_fields and key not in _SETTINGS_FROZEN_FIELDS:
                setattr(self, key, value)

    # ── Flattened values for API responses ──────────────────────────

    def agent_settings_values(self) -> dict[str, Any]:
        """Return agent settings as a flat dotted-key dict for API responses."""
        field_keys, _ = _sdk_schema_field_metadata()
        payload = self.agent_settings.model_dump(
            mode="json", context={"expose_secrets": True}
        )
        values: dict[str, Any] = {
            "schema_version": payload.get(
                "schema_version",
                AgentSettings.model_fields["schema_version"].default,
            )
        }
        for key in field_keys:
            value = _lookup_dotted(payload, key)
            if value is not None:
                values[key] = _normalize_model_name(key, value)
        return values

    # ── Serialization ───────────────────────────────────────────────

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

    @field_serializer("agent_settings")
    def agent_settings_serializer(
        self, agent_settings: AgentSettings, info: SerializationInfo
    ) -> dict[str, Any]:
        context = info.context or {}
        if context.get("expose_secrets", False):
            return agent_settings.model_dump(
                mode="json", context={"expose_secrets": True}
            )
        return agent_settings.model_dump(mode="json")

    # ── Legacy migration (model_validator) ──────────────────────────

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: dict | object) -> dict | object:
        """Migrate legacy flat fields into ``agent_settings`` and ``conversation_settings``."""
        if not isinstance(data, dict):
            return data

        # --- Agent settings ---
        agent_settings = data.pop("agent_settings", None)
        # Accept raw_agent_settings as an alias for backward compat with persisted data
        raw_agent_settings = data.pop("raw_agent_settings", None)
        agent_vals: dict[str, Any] = {}
        source = raw_agent_settings or agent_settings
        if isinstance(source, AgentSettings):
            agent_vals = source.model_dump(
                mode="json", context={"expose_secrets": True}
            )
        elif isinstance(source, dict):
            agent_vals = dict(source)

        # Normalize MCP config if present (legacy dict → SDK format)
        mcp_val = agent_vals.get("mcp_config")
        if mcp_val is not None:
            agent_vals["mcp_config"] = _normalize_mcp_value(mcp_val)

        # Migrate legacy top-level keys (sdk_settings_values, mcp_config)
        for legacy_key in ("sdk_settings_values", "mcp_config"):
            legacy_val = data.pop(legacy_key, None)
            if legacy_key == "sdk_settings_values" and isinstance(legacy_val, dict):
                for key, value in legacy_val.items():
                    agent_vals.setdefault(key, _coerce_value(value))
            elif legacy_key == "mcp_config" and legacy_val is not None:
                agent_vals.setdefault("mcp_config", _normalize_mcp_value(legacy_val))

        # Migrate legacy flat fields → nested SDK dict structure
        for flat_key, path in _LEGACY_FLAT_TO_SDK.items():
            if flat_key not in data:
                continue
            value = data[flat_key]
            if value is not None:
                if isinstance(value, str) and value.startswith("**"):
                    continue
                coerced = _coerce_value(value)
                # Only set if the SDK path isn't already populated
                if _lookup_dotted(agent_vals, ".".join(path)) is None:
                    _set_nested(agent_vals, path, coerced)

        # Strip conversation settings keys that may have leaked into agent_settings
        for conv_key in _CONVERSATION_SETTINGS_KEYS:
            agent_vals.pop(conv_key, None)

        # Remove flat legacy keys from data
        for flat_key in _LEGACY_FLAT_TO_SDK:
            data.pop(flat_key, None)

        # Expand any remaining dotted keys to nested dicts
        expanded: dict[str, Any] = {}
        for key, value in agent_vals.items():
            if "." in key:
                _set_nested(expanded, key.split("."), _coerce_value(value))
            else:
                expanded[key] = (
                    _coerce_value(value) if not isinstance(value, dict) else value
                )
        agent_vals = expanded

        data["agent_settings"] = agent_vals

        # --- Conversation settings ---
        conversation_settings = data.pop('conversation_settings', None)
        conversation_vals: dict[str, Any] = {}
        if isinstance(conversation_settings, dict):
            conversation_vals = conversation_settings
        elif isinstance(conversation_settings, ConversationSettings):
            conversation_vals = conversation_settings.model_dump(mode='json')

        for flat_key in _CONVERSATION_SETTINGS_KEYS:
            if flat_key in data:
                value = data.pop(flat_key)
                if value is not None and flat_key not in conversation_vals:
                    conversation_vals[flat_key] = value

        if conversation_vals:
            data["conversation_settings"] = conversation_vals

        # --- Secrets store ---
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

    @field_serializer("secrets_store")
    def secrets_store_serializer(self, secrets: Secrets, info: SerializationInfo):
        return {'provider_tokens': {}}

    # ── Factory methods ─────────────────────────────────────────────

    @staticmethod
    def from_config() -> Settings | None:
        app_config = load_openhands_config()
        llm_config: LLMConfig = app_config.get_llm_config()
        if llm_config.api_key is None:
            return None

        agent_settings_dict: dict[str, Any] = {
            "agent": app_config.default_agent,
            "llm": {
                "model": llm_config.model,
                "api_key": (
                    llm_config.api_key.get_secret_value()
                    if isinstance(llm_config.api_key, SecretStr)
                    else llm_config.api_key
                ),
                "base_url": llm_config.base_url,
            },
        }
        if hasattr(app_config, "mcp") and app_config.mcp:
            agent_settings_dict["mcp_config"] = _coerce_value(app_config.mcp)

        return Settings(
            language="en",
            remote_runtime_resource_factor=app_config.sandbox.remote_runtime_resource_factor,
            search_api_key=app_config.search_api_key,
            max_budget_per_task=app_config.max_budget_per_task,
            agent_settings=agent_settings_dict,  # type: ignore[arg-type]
            conversation_settings=ConversationSettings(
                confirmation_mode=bool(app_config.security.confirmation_mode),
                security_analyzer=app_config.security.security_analyzer,
                max_iterations=app_config.max_iterations,
            ),
        )

    def merge_with_config_settings(self) -> "Settings":
        """Merge config.toml MCP settings with stored SDK agent_settings."""
        config_settings = Settings.from_config()
        if not config_settings:
            return self

        merged_mcp = _merge_sdk_mcp_configs(
            config_settings.agent_settings.mcp_config,
            self.agent_settings.mcp_config,
        )
        if merged_mcp is None:
            return self

        self.agent_settings.mcp_config = merged_mcp
        return self

    def to_agent_settings(self) -> AgentSettings:
        return self.agent_settings
