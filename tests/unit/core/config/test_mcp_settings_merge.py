"""Test MCP settings merging functionality."""

import os
from unittest.mock import patch

import pytest

from openhands.core.config.mcp_config import (
    MCPConfig,
    MCPRemoteServerConfig,
    MCPStdioServerConfig,
)
from openhands.storage.data_models.settings import Settings


@pytest.fixture(autouse=True)
def allow_short_context_windows():
    with patch.dict(os.environ, {'ALLOW_SHORT_CONTEXT_WINDOWS': 'true'}, clear=False):
        yield


def _mcp_config(settings: Settings) -> MCPConfig | None:
    mcp = settings.agent_settings.mcp_config
    return mcp if mcp and mcp.mcpServers else None


@pytest.mark.asyncio
async def test_mcp_settings_merge_config_only():
    """Test merging when only config.toml has MCP settings."""
    mock_config_settings = Settings(
        mcp_config=MCPConfig(
            mcpServers={
                'config': MCPRemoteServerConfig(url='http://config-server.com', transport='sse')
            }
        )
    )

    frontend_settings = Settings(llm_model='gpt-4')

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.mcpServers) == 1
    assert 'config' in merged_mcp_config.mcpServers
    assert merged_settings.llm_model == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_frontend_only():
    """Test merging when only frontend has MCP settings."""
    mock_config_settings = Settings(llm_model='claude-3')

    frontend_settings = Settings(
        llm_model='gpt-4',
        mcp_config=MCPConfig(
            mcpServers={
                'frontend': MCPRemoteServerConfig(url='http://frontend-server.com', transport='sse')
            }
        ),
    )

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.mcpServers) == 1
    assert 'frontend' in merged_mcp_config.mcpServers
    assert merged_settings.llm_model == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_both_present():
    """Test merging when both config.toml and frontend have MCP settings."""
    mock_config_settings = Settings(
        mcp_config=MCPConfig(
            mcpServers={
                'config-sse': MCPRemoteServerConfig(url='http://config-server.com', transport='sse'),
                'config-stdio': MCPStdioServerConfig(command='config-cmd', args=['arg1']),
            }
        )
    )

    frontend_settings = Settings(
        llm_model='gpt-4',
        mcp_config=MCPConfig(
            mcpServers={
                'frontend-sse': MCPRemoteServerConfig(url='http://frontend-server.com', transport='sse'),
                'frontend-stdio': MCPStdioServerConfig(command='frontend-cmd', args=['arg2']),
            }
        ),
    )

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.mcpServers) == 4
    assert 'config-sse' in merged_mcp_config.mcpServers
    assert 'frontend-sse' in merged_mcp_config.mcpServers
    assert 'config-stdio' in merged_mcp_config.mcpServers
    assert 'frontend-stdio' in merged_mcp_config.mcpServers
    assert merged_settings.llm_model == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_no_config():
    """Test merging when config.toml has no MCP settings."""
    mock_config_settings = None

    frontend_settings = Settings(
        llm_model='gpt-4',
        mcp_config=MCPConfig(
            mcpServers={
                'frontend': MCPRemoteServerConfig(url='http://frontend-server.com', transport='sse')
            }
        ),
    )

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.mcpServers) == 1
    assert merged_settings.llm_model == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_neither_present():
    """Test merging when neither config.toml nor frontend have MCP settings."""
    mock_config_settings = Settings(llm_model='claude-3')

    frontend_settings = Settings(llm_model='gpt-4')

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    assert _mcp_config(merged_settings) is None
    assert merged_settings.llm_model == 'gpt-4'
