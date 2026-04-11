from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openhands.core.config.openhands_config import OpenHandsConfig

from openhands.core.config.mcp_config import (
    MCPRemoteServerConfig,
    MCPStdioServerConfig,
    OpenHandsMCPConfig,
)
from openhands.core.logger import openhands_logger as logger


class SaaSOpenHandsMCPConfig(OpenHandsMCPConfig):
    @staticmethod
    async def create_default_mcp_server_config(
        host: str, config: 'OpenHandsConfig', user_id: str | None = None
    ) -> dict[str, MCPRemoteServerConfig | MCPStdioServerConfig]:
        """Return a dict of default MCP server entries for SaaS mode."""
        from storage.api_key_store import ApiKeyStore

        api_key_store = ApiKeyStore.get_instance()
        if user_id:
            api_key = await api_key_store.retrieve_mcp_api_key(user_id)

            if not api_key:
                api_key = await api_key_store.create_api_key(
                    user_id, 'MCP_API_KEY', None
                )

            if not api_key:
                logger.error(f'Could not provision MCP API Key for user: {user_id}')
                return {}

            return {
                'openhands': MCPRemoteServerConfig(
                    url=f'https://{host}/mcp/mcp',
                    transport='http',
                    auth=api_key,
                    timeout=60,
                )
            }
        return {}
