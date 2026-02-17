"""
Permission-based authorization dependencies for API endpoints (SAAS mode).

This module provides FastAPI dependencies for checking user permissions
within organizations. It uses a permission-based authorization model where
roles (owner, admin, member) are mapped to specific permissions.

This is the SAAS/enterprise implementation that performs real authorization
checks against the database.

Usage:
    from server.auth.authorization import (
        Permission,
        require_permission,
        require_org_role,
        require_org_user,
        require_org_admin,
        require_org_owner,
    )

    @router.get('/{org_id}/settings')
    async def get_settings(
        org_id: UUID,
        user_id: str = Depends(require_permission(Permission.VIEW_LLM_SETTINGS)),
    ):
        # Only users with VIEW_LLM_SETTINGS permission can access
        ...
"""

from enum import Enum
from uuid import UUID

from fastapi import Depends, HTTPException, status
from storage.org_member_store import OrgMemberStore
from storage.role import Role
from storage.role_store import RoleStore

from openhands.core.logger import openhands_logger as logger
from openhands.server.auth import Permission
from openhands.server.user_auth import get_user_id


class RoleName(str, Enum):
    """Role names used in the system."""

    OWNER = 'owner'
    ADMIN = 'admin'
    MEMBER = 'member'


# Permission mappings for each role
ROLE_PERMISSIONS: dict[RoleName, frozenset[Permission]] = {
    RoleName.OWNER: frozenset(
        [
            # Settings (Full access)
            Permission.MANAGE_SECRETS,
            Permission.MANAGE_MCP,
            Permission.MANAGE_INTEGRATIONS,
            Permission.MANAGE_APPLICATION_SETTINGS,
            Permission.MANAGE_API_KEYS,
            Permission.VIEW_LLM_SETTINGS,
            Permission.EDIT_LLM_SETTINGS,
            Permission.VIEW_BILLING,
            Permission.ADD_CREDITS,
            # Organization Members
            Permission.INVITE_USER_TO_ORGANIZATION,
            Permission.CHANGE_USER_ROLE_MEMBER,
            Permission.CHANGE_USER_ROLE_ADMIN,
            Permission.CHANGE_USER_ROLE_OWNER,
            # Organization Management (Owner only)
            Permission.CHANGE_ORGANIZATION_NAME,
            Permission.DELETE_ORGANIZATION,
        ]
    ),
    RoleName.ADMIN: frozenset(
        [
            # Settings (Full access)
            Permission.MANAGE_SECRETS,
            Permission.MANAGE_MCP,
            Permission.MANAGE_INTEGRATIONS,
            Permission.MANAGE_APPLICATION_SETTINGS,
            Permission.MANAGE_API_KEYS,
            Permission.VIEW_LLM_SETTINGS,
            Permission.EDIT_LLM_SETTINGS,
            Permission.VIEW_BILLING,
            Permission.ADD_CREDITS,
            # Organization Members
            Permission.INVITE_USER_TO_ORGANIZATION,
            Permission.CHANGE_USER_ROLE_MEMBER,
            Permission.CHANGE_USER_ROLE_ADMIN,
        ]
    ),
    RoleName.MEMBER: frozenset(
        [
            # Settings (Full access)
            Permission.MANAGE_SECRETS,
            Permission.MANAGE_MCP,
            Permission.MANAGE_INTEGRATIONS,
            Permission.MANAGE_APPLICATION_SETTINGS,
            Permission.MANAGE_API_KEYS,
            # LLM Settings (View only)
            Permission.VIEW_LLM_SETTINGS,
        ]
    ),
}


def get_role_permissions(role_name: str) -> frozenset[Permission]:
    """Get the permissions for a role."""
    try:
        role_enum = RoleName(role_name)
        return ROLE_PERMISSIONS.get(role_enum, frozenset())
    except ValueError:
        return frozenset()


def get_user_org_role(user_id: str, org_id: UUID) -> Role | None:
    """
    Get the user's role in an organization.

    Args:
        user_id: User ID (string that will be converted to UUID)
        org_id: Organization ID

    Returns:
        Role object if user is a member, None otherwise
    """
    from uuid import UUID as parse_uuid

    org_member = OrgMemberStore.get_org_member(org_id, parse_uuid(user_id))
    if not org_member:
        return None

    return RoleStore.get_role_by_id(org_member.role_id)


def has_permission(user_role: Role, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        user_role: User's Role object
        permission: Permission to check

    Returns:
        True if the role has the permission
    """
    permissions = get_role_permissions(user_role.name)
    return permission in permissions


def has_required_role(user_role: Role, required_role: Role) -> bool:
    """
    Check if user's role meets or exceeds the required role.

    Uses role hierarchy based on rank where lower rank = higher position
    (e.g., rank 1 owner > rank 2 admin > rank 3 user).

    Args:
        user_role: User's actual Role object
        required_role: Minimum required Role object

    Returns:
        True if user has sufficient permissions
    """
    return user_role.rank <= required_role.rank


def require_permission(permission: Permission):
    """
    Factory function that creates a dependency to require a specific permission.

    This creates a FastAPI dependency that:
    1. Extracts org_id from the path parameter
    2. Gets the authenticated user_id
    3. Checks if the user has the required permission in the organization
    4. Returns the user_id if authorized, raises HTTPException otherwise

    Usage:
        @router.get('/{org_id}/settings')
        async def get_settings(
            org_id: UUID,
            user_id: str = Depends(require_permission(Permission.VIEW_LLM_SETTINGS)),
        ):
            ...

    Args:
        permission: The permission required to access the endpoint

    Returns:
        Dependency function that validates permission and returns user_id
    """

    async def permission_checker(
        org_id: UUID,
        user_id: str | None = Depends(get_user_id),
    ) -> str:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='User not authenticated',
            )

        user_role = get_user_org_role(user_id, org_id)

        if not user_role:
            logger.warning(
                'User not a member of organization',
                extra={'user_id': user_id, 'org_id': str(org_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='User is not a member of this organization',
            )

        if not has_permission(user_role, permission):
            logger.warning(
                'Insufficient permissions',
                extra={
                    'user_id': user_id,
                    'org_id': str(org_id),
                    'user_role': user_role.name,
                    'required_permission': permission.value,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Requires {permission.value} permission',
            )

        return user_id

    return permission_checker


def require_org_role(required_role_name: str):
    """
    Factory function that creates a dependency to require a minimum org role.

    This creates a FastAPI dependency that:
    1. Extracts org_id from the path parameter
    2. Gets the authenticated user_id
    3. Checks if the user has the required role in the organization
    4. Returns the user_id if authorized, raises HTTPException otherwise

    Role hierarchy is based on rank from the Role class, where
    lower rank = higher position (e.g., rank 1 > rank 2 > rank 3).

    Usage:
        @router.get('/{org_id}/resource')
        async def get_resource(
            org_id: UUID,
            user_id: str = Depends(require_org_role('user')),
        ):
            ...

    Args:
        required_role_name: Name of the minimum required role to access the endpoint

    Returns:
        Dependency function that validates role and returns user_id
    """

    async def role_checker(
        org_id: UUID,
        user_id: str | None = Depends(get_user_id),
    ) -> str:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='User not authenticated',
            )

        user_role = get_user_org_role(user_id, org_id)

        if not user_role:
            logger.warning(
                'User not a member of organization',
                extra={'user_id': user_id, 'org_id': str(org_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='User is not a member of this organization',
            )

        required_role = RoleStore.get_role_by_name(required_role_name)
        if not required_role:
            logger.error(
                'Required role not found in database',
                extra={'required_role': required_role_name},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Role configuration error',
            )

        if not has_required_role(user_role, required_role):
            logger.warning(
                'Insufficient role permissions',
                extra={
                    'user_id': user_id,
                    'org_id': str(org_id),
                    'user_role': user_role.name,
                    'required_role': required_role_name,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Requires {required_role_name} role or higher',
            )

        return user_id

    return role_checker


# Convenience dependencies for common role checks
require_org_user = require_org_role('user')
require_org_admin = require_org_role('admin')
require_org_owner = require_org_role('owner')
