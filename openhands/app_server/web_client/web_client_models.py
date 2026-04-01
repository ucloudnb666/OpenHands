import os
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from openhands.agent_server.env_parser import DiscriminatedUnionMixin
from openhands.integrations.service_types import ProviderType
from openhands.server.types import AppMode

DeploymentMode = Literal['cloud', 'self_hosted']


# This can be removed / replaced when a DeploymentMode (or similar) env var is created.
def _get_deployment_mode() -> DeploymentMode | None:
    """Get deployment mode based on OH_WEB_HOST environment variable."""
    web_host = os.getenv('OH_WEB_HOST', os.getenv('WEB_HOST', '')).strip()
    if not web_host:
        return None
    if (
        web_host == 'app.all-hands.dev'
        or web_host == 'app.openhands.ai'
        or web_host.endswith('.all-hands.dev')
        or web_host.endswith('.openhands.ai')
        or web_host == 'localhost'
    ):
        return 'cloud'
    return 'self_hosted'


class WebClientFeatureFlags(BaseModel):
    enable_billing: bool = False
    hide_llm_settings: bool = False
    enable_jira: bool = False
    enable_jira_dc: bool = False
    enable_linear: bool = False
    hide_users_page: bool = False
    hide_billing_page: bool = False
    hide_integrations_page: bool = False
    deployment_mode: DeploymentMode | None = None

    @model_validator(mode='after')
    def set_deployment_mode(self) -> 'WebClientFeatureFlags':
        if self.deployment_mode is None:
            self.deployment_mode = _get_deployment_mode()
        return self


class WebClientConfig(DiscriminatedUnionMixin):
    app_mode: AppMode
    posthog_client_key: str | None
    feature_flags: WebClientFeatureFlags
    providers_configured: list[ProviderType]
    maintenance_start_time: datetime | None
    auth_url: str | None
    recaptcha_site_key: str | None
    faulty_models: list[str]
    error_message: str | None
    updated_at: datetime
    github_app_slug: str | None
