# IMPORTANT: LEGACY V0 CODE - Deprecated since version 1.0.0, scheduled for removal April 1, 2026
# This file is part of the legacy (V0) implementation of OpenHands and will be removed soon as we complete the migration to V1.
# OpenHands V1 uses the Software Agent SDK for the agentic core and runs a new application server. Please refer to:
#   - V1 agentic core (SDK): https://github.com/OpenHands/software-agent-sdk
#   - V1 application server (in this repo): openhands/app_server/
# Unless you are working on deprecation, please avoid extending this legacy file and consult the V1 codepaths above.
# Tag: Legacy-V0
# This module belongs to the old V0 web server. The V1 application server lives under openhands/app_server/.
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from openhands.core.logger import openhands_logger as logger
from openhands.integrations.provider import (
    PROVIDER_TOKEN_TYPE,
    ProviderType,
)
from openhands.sdk.settings import AgentSettings
from openhands.server.dependencies import get_dependencies
from openhands.server.routes.secrets import invalidate_legacy_secrets_store
from openhands.server.settings import (
    GETSettingsModel,
)
from openhands.server.shared import config
from openhands.server.user_auth import (
    get_provider_tokens,
    get_secrets_store,
    get_user_settings,
    get_user_settings_store,
)
from openhands.storage.data_models.settings import Settings
from openhands.storage.secrets.secrets_store import SecretsStore
from openhands.storage.settings.settings_store import SettingsStore


def _get_agent_settings_schema() -> dict[str, Any]:
    """Return the SDK agent settings schema for the legacy V0 settings API."""
    return AgentSettings.export_schema().model_dump(mode='json')


def _get_schema_field_keys(schema: dict[str, Any] | None) -> set[str]:
    if not schema:
        return set()
    return {
        field['key']
        for section in schema.get('sections', [])
        for field in section.get('fields', [])
    }


def _get_schema_secret_field_keys(schema: dict[str, Any] | None) -> set[str]:
    if not schema:
        return set()
    return {
        field['key']
        for section in schema.get('sections', [])
        for field in section.get('fields', [])
        if field.get('secret')
    }


_SECRET_REDACTED = '<hidden>'


def _extract_agent_settings(
    settings: Settings, schema: dict[str, Any] | None
) -> dict[str, Any]:
    """Build the agent_settings dict for the GET response.

    Secret fields with a value are redacted to ``"<hidden>"``;
    unset secrets become ``None``.
    """
    values = settings.agent_settings_values()
    for field_key in _get_schema_secret_field_keys(schema):
        raw = values.get(field_key)
        values[field_key] = _SECRET_REDACTED if raw else None
    return values


_SETTINGS_FROZEN_FIELDS = frozenset(
    name for name, field_info in Settings.model_fields.items() if field_info.frozen
)


def _apply_settings_payload(
    payload: dict[str, Any],
    existing_settings: Settings | None,
    agent_schema: dict[str, Any] | None,
) -> Settings:
    """Apply an incoming settings payload.

    SDK dotted keys (e.g. ``llm.model``) go into ``agent_settings``.
    Other keys (e.g. ``language``, ``git_user_name``) are set directly
    on the ``Settings`` model.
    """
    settings = existing_settings.model_copy() if existing_settings else Settings()

    schema_field_keys = _get_schema_field_keys(agent_schema)
    secret_field_keys = _get_schema_secret_field_keys(agent_schema)
    agent_settings = dict(settings.raw_agent_settings)

    for key, value in payload.items():
        if key in schema_field_keys:
            if key in secret_field_keys:
                if value is not None and value != '' and value != _SECRET_REDACTED:
                    agent_settings[key] = value
            elif value is None:
                agent_settings.pop(key, None)
            else:
                agent_settings[key] = value
        elif key in Settings.model_fields and key not in _SETTINGS_FROZEN_FIELDS:
            setattr(settings, key, value)

    object.__setattr__(settings, 'raw_agent_settings', agent_settings)
    settings.normalize_agent_settings()
    return settings


app = APIRouter(prefix='/api', dependencies=get_dependencies())


@app.get(
    '/settings',
    response_model=GETSettingsModel,
    responses={
        404: {'description': 'Settings not found', 'model': dict},
        401: {'description': 'Invalid token', 'model': dict},
    },
)
async def load_settings(
    provider_tokens: PROVIDER_TOKEN_TYPE | None = Depends(get_provider_tokens),
    settings_store: SettingsStore = Depends(get_user_settings_store),
    settings: Settings = Depends(get_user_settings),
    secrets_store: SecretsStore = Depends(get_secrets_store),
) -> GETSettingsModel | JSONResponse:
    try:
        if not settings:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={'error': 'Settings not found'},
            )

        # On initial load, user secrets may not be populated with values migrated from settings store
        user_secrets = await invalidate_legacy_secrets_store(
            settings, settings_store, secrets_store
        )

        # If invalidation is successful, then the returned user secrets holds the most recent values
        git_providers = (
            user_secrets.provider_tokens if user_secrets else provider_tokens
        )

        provider_tokens_set: dict[ProviderType, str | None] = {}
        if git_providers:
            for provider_type, provider_token in git_providers.items():
                if provider_token.token or provider_token.user_id:
                    provider_tokens_set[provider_type] = provider_token.host

        agent_settings_schema = _get_agent_settings_schema()
        agent_vals = _extract_agent_settings(settings, agent_settings_schema)

        settings_with_token_data = GETSettingsModel(
            **settings.model_dump(exclude={'secrets_store', 'raw_agent_settings'}),
            llm_api_key_set=settings.llm_api_key_is_set,
            search_api_key_set=settings.search_api_key is not None
            and bool(settings.search_api_key),
            provider_tokens_set=provider_tokens_set,
            agent_settings_schema=agent_settings_schema,
            agent_settings=agent_vals,
        )

        # Redact secrets from the response.
        settings_with_token_data.search_api_key = None
        settings_with_token_data.sandbox_api_key = None
        return settings_with_token_data
    except Exception as e:
        logger.warning(f'Invalid token: {e}')
        user_id = getattr(settings, 'user_id', 'unknown') if settings else 'unknown'
        logger.info(
            f'Returning 401 Unauthorized - Invalid token for user_id: {user_id}'
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={'error': 'Invalid token'},
        )


# NOTE: We use response_model=None for endpoints that return JSONResponse directly.
# This is because FastAPI's response_model expects a Pydantic model, but we're returning
# a response object directly. We document the possible responses using the 'responses'
# parameter and maintain proper type annotations for mypy.
@app.post(
    '/settings',
    response_model=None,
    responses={
        200: {'description': 'Settings stored successfully', 'model': dict},
        500: {'description': 'Error storing settings', 'model': dict},
    },
)
async def store_settings(
    payload: dict[str, Any],
    settings_store: SettingsStore = Depends(get_user_settings_store),
) -> JSONResponse:
    try:
        existing_settings = await settings_store.load()
        agent_settings_schema = _get_agent_settings_schema()
        settings = _apply_settings_payload(
            payload, existing_settings, agent_settings_schema
        )

        if existing_settings:
            if not settings.search_api_key:
                settings.search_api_key = existing_settings.search_api_key
            if settings.user_consents_to_analytics is None:
                settings.user_consents_to_analytics = (
                    existing_settings.user_consents_to_analytics
                )

        # Update sandbox config with new settings
        if settings.remote_runtime_resource_factor is not None:
            config.sandbox.remote_runtime_resource_factor = (
                settings.remote_runtime_resource_factor
            )

        # Update git configuration with new settings
        git_config_updated = False
        if settings.git_user_name is not None:
            config.git_user_name = settings.git_user_name
            git_config_updated = True
        if settings.git_user_email is not None:
            config.git_user_email = settings.git_user_email
            git_config_updated = True

        if git_config_updated:
            logger.info(
                f'Updated global git configuration: name={config.git_user_name}, email={config.git_user_email}'
            )

        await settings_store.store(settings)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'message': 'Settings stored'},
        )
    except Exception as e:
        logger.warning(f'Something went wrong storing settings: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={'error': 'Something went wrong storing settings'},
        )
