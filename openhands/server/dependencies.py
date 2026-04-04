# IMPORTANT: LEGACY V0 CODE - Deprecated since version 1.0.0, scheduled for removal April 1, 2026
# This compatibility shim preserves legacy V0 imports while the shared
# dependency helpers live under the V1 application server package.

from openhands.app_server.utils.dependencies import get_dependencies

__all__ = ['get_dependencies']
