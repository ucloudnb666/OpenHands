"""Test MCP settings merging functionality."""

import os
from unittest.mock import patch

import pytest

from openhands.core.config.mcp_config import (
    MCPConfig,
    MCPSSEServerConfig,
    MCPStdioServerConfig,
)
from openhands.storage.data_models.settings import Settings


@pytest.fixture(autouse=True)
def allow_short_context_windows():
    with patch.dict(os.environ, {'ALLOW_SHORT_CONTEXT_WINDOWS': 'true'}, clear=False):
        yield


def _mcp_config(settings: Settings) -> MCPConfig | None:
    return settings.to_legacy_mcp_config()


@pytest.mark.asyncio
async def test_mcp_settings_merge_config_only():
    """Test merging when only config.toml has MCP settings."""
    # Mock config.toml with MCP settings
    mock_config_settings = Settings(
        mcp_config=MCPConfig(
            sse_servers=[MCPSSEServerConfig(url='http://config-server.com')]
        )
    )

    # Frontend settings without MCP config
    frontend_settings = Settings(llm_model='gpt-4')

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    # Should use config.toml MCP settings
    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.sse_servers) == 1
    assert merged_mcp_config.sse_servers[0].url == 'http://config-server.com'
    assert merged_settings.get_agent_setting('llm.model') == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_frontend_only():
    """Test merging when only frontend has MCP settings."""
    # Mock config.toml without MCP settings
    mock_config_settings = Settings(llm_model='claude-3')

    # Frontend settings with MCP config
    frontend_settings = Settings(
        llm_model='gpt-4',
        mcp_config=MCPConfig(
            sse_servers=[MCPSSEServerConfig(url='http://frontend-server.com')]
        ),
    )

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    # Should keep frontend MCP settings
    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.sse_servers) == 1
    assert merged_mcp_config.sse_servers[0].url == 'http://frontend-server.com'
    assert merged_settings.get_agent_setting('llm.model') == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_both_present():
    """Test merging when both config.toml and frontend have MCP settings."""
    # Mock config.toml with MCP settings
    mock_config_settings = Settings(
        mcp_config=MCPConfig(
            sse_servers=[MCPSSEServerConfig(url='http://config-server.com')],
            stdio_servers=[
                MCPStdioServerConfig(
                    name='config-stdio', command='config-cmd', args=['arg1']
                )
            ],
        )
    )

    # Frontend settings with different MCP config
    frontend_settings = Settings(
        llm_model='gpt-4',
        mcp_config=MCPConfig(
            sse_servers=[MCPSSEServerConfig(url='http://frontend-server.com')],
            stdio_servers=[
                MCPStdioServerConfig(
                    name='frontend-stdio', command='frontend-cmd', args=['arg2']
                )
            ],
        ),
    )

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    # Should merge both with config.toml taking priority (appearing first)
    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.sse_servers) == 2
    assert merged_mcp_config.sse_servers[0].url == 'http://config-server.com'
    assert merged_mcp_config.sse_servers[1].url == 'http://frontend-server.com'

    assert len(merged_mcp_config.stdio_servers) == 2
    assert merged_mcp_config.stdio_servers[0].name == 'config-stdio'
    assert merged_mcp_config.stdio_servers[1].name == 'frontend-stdio'

    assert merged_settings.get_agent_setting('llm.model') == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_no_config():
    """Test merging when config.toml has no MCP settings."""
    # Mock config.toml without MCP settings
    mock_config_settings = None

    # Frontend settings with MCP config
    frontend_settings = Settings(
        llm_model='gpt-4',
        mcp_config=MCPConfig(
            sse_servers=[MCPSSEServerConfig(url='http://frontend-server.com')]
        ),
    )

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    # Should keep frontend settings unchanged
    merged_mcp_config = _mcp_config(merged_settings)
    assert merged_mcp_config is not None
    assert len(merged_mcp_config.sse_servers) == 1
    assert merged_mcp_config.sse_servers[0].url == 'http://frontend-server.com'
    assert merged_settings.get_agent_setting('llm.model') == 'gpt-4'


@pytest.mark.asyncio
async def test_mcp_settings_merge_neither_present():
    """Test merging when neither config.toml nor frontend have MCP settings."""
    # Mock config.toml without MCP settings
    mock_config_settings = Settings(llm_model='claude-3')

    # Frontend settings without MCP config
    frontend_settings = Settings(llm_model='gpt-4')

    with patch.object(Settings, 'from_config', return_value=mock_config_settings):
        merged_settings = frontend_settings.merge_with_config_settings()

    # Should keep frontend settings unchanged
    assert _mcp_config(merged_settings) is None
    assert merged_settings.get_agent_setting('llm.model') == 'gpt-4'
