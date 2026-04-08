from openhands.integrations.provider import PROVIDER_TOKEN_TYPE
from openhands.storage.data_models.settings import Settings


class UserInfo(Settings):
    """Model for user settings including the current user id.

    SAAS-only fields (org_id, org_name, role, permissions) are populated
    when running in SAAS mode and the user is authenticated.
    """

    id: str | None = None
    # SAAS-only fields
    org_id: str | None = None
    org_name: str | None = None
    role: str | None = None
    permissions: list[str] | None = None


class ProviderTokenPage:
    items: list[PROVIDER_TOKEN_TYPE]
    next_page_id: str | None = None
