"""
Permission-based authorization for API endpoints (OSS/OpenHands mode).

In OSS mode, authorization is a no-op - all checks pass.
For SAAS mode with real authorization checks, see the enterprise implementation.
"""

from enum import Enum
from uuid import UUID

from fastapi import Depends

from openhands.server.user_auth import get_user_id


class Permission(str, Enum):
    """Permissions that can be checked in authorization."""

    MANAGE_SECRETS = 'manage_secrets'
    MANAGE_MCP = 'manage_mcp'
    MANAGE_INTEGRATIONS = 'manage_integrations'
    MANAGE_APPLICATION_SETTINGS = 'manage_application_settings'
    MANAGE_API_KEYS = 'manage_api_keys'
    VIEW_LLM_SETTINGS = 'view_llm_settings'
    EDIT_LLM_SETTINGS = 'edit_llm_settings'
    VIEW_BILLING = 'view_billing'
    ADD_CREDITS = 'add_credits'
    INVITE_USER_TO_ORGANIZATION = 'invite_user_to_organization'
    CHANGE_USER_ROLE_MEMBER = 'change_user_role:member'
    CHANGE_USER_ROLE_ADMIN = 'change_user_role:admin'
    CHANGE_USER_ROLE_OWNER = 'change_user_role:owner'
    CHANGE_ORGANIZATION_NAME = 'change_organization_name'
    DELETE_ORGANIZATION = 'delete_organization'


def require_permission(permission: Permission):
    """
    No-op authorization dependency for OSS mode.

    Returns the user_id without performing any permission checks.
    In SAAS mode, the enterprise implementation overrides this.
    """

    async def permission_checker(
        org_id: UUID,
        user_id: str | None = Depends(get_user_id),
    ) -> str | None:
        return user_id

    return permission_checker
