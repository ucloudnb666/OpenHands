"""
Authorization module for OpenHands.

In OSS mode, authorization is a no-op - all checks pass.
In SAAS mode, the enterprise implementation performs real authorization checks.
"""

from openhands.server.auth.authorization import (
    Permission,
    require_permission,
)

__all__ = [
    'Permission',
    'require_permission',
]
