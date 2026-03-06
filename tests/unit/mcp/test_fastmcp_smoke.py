"""Smoke tests to verify fastmcp upgrade works correctly.

These tests exercise real fastmcp functionality without mocking the core
components, ensuring the upgrade maintains compatibility with OpenHands.
"""

import asyncio

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import TextContent


class TestFastMCPServerCreation:
    """Test FastMCP server creation and configuration."""

    def test_create_basic_server(self):
        """Test creating a basic FastMCP server."""
        server = FastMCP('test-server')
        assert server is not None
        assert server.name == 'test-server'

    def test_create_server_with_mask_error_details(self):
        """Test creating server with mask_error_details option."""
        server = FastMCP('secure-server', mask_error_details=True)
        assert server is not None

    def test_register_tool_decorator(self):
        """Test registering a tool using the decorator."""
        server = FastMCP('tool-test')

        @server.tool()
        def sample_tool(x: int) -> int:
            """Sample tool for testing."""
            return x * 2

        # Verify the tool is registered
        tools = server._tool_manager._tools
        assert 'sample_tool' in tools


class TestFastMCPToolExecution:
    """Test real tool execution through fastmcp client-server interaction."""

    @pytest.mark.asyncio
    async def test_sync_tool_execution(self):
        """Test executing a synchronous tool."""
        server = FastMCP('sync-tool-test')

        @server.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        async with Client(server) as client:
            result = await client.call_tool('add', {'a': 5, 'b': 3})

        assert result.data == 8
        assert result.is_error is False
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == '8'

    @pytest.mark.asyncio
    async def test_async_tool_execution(self):
        """Test executing an asynchronous tool."""
        server = FastMCP('async-tool-test')

        @server.tool()
        async def async_multiply(a: int, b: int) -> int:
            """Async multiply two numbers."""
            await asyncio.sleep(0.001)  # Simulate async operation
            return a * b

        async with Client(server) as client:
            result = await client.call_tool('async_multiply', {'a': 4, 'b': 5})

        assert result.data == 20
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_string_result_tool(self):
        """Test tool returning a string result."""
        server = FastMCP('string-tool-test')

        @server.tool()
        def greet(name: str) -> str:
            """Greet someone by name."""
            return f'Hello, {name}!'

        async with Client(server) as client:
            result = await client.call_tool('greet', {'name': 'FastMCP'})

        assert result.data == 'Hello, FastMCP!'
        assert result.content[0].text == 'Hello, FastMCP!'

    @pytest.mark.asyncio
    async def test_complex_return_type(self):
        """Test tool returning a complex object."""
        server = FastMCP('complex-return-test')

        @server.tool()
        def get_info() -> dict:
            """Return a dictionary."""
            return {'status': 'ok', 'count': 42, 'items': ['a', 'b', 'c']}

        async with Client(server) as client:
            result = await client.call_tool('get_info', {})

        assert result.data == {'status': 'ok', 'count': 42, 'items': ['a', 'b', 'c']}
        assert result.is_error is False


class TestFastMCPToolListing:
    """Test tool discovery through fastmcp client."""

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools from server."""
        server = FastMCP('list-tools-test')

        @server.tool()
        def tool_one(x: int) -> int:
            """First tool."""
            return x

        @server.tool()
        def tool_two(s: str) -> str:
            """Second tool."""
            return s

        async with Client(server) as client:
            tools = await client.list_tools()

        tool_names = [t.name for t in tools]
        assert 'tool_one' in tool_names
        assert 'tool_two' in tool_names
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_tool_metadata(self):
        """Test that tool metadata is properly exposed."""
        server = FastMCP('metadata-test')

        @server.tool()
        def documented_tool(value: int) -> int:
            """This tool has documentation."""
            return value

        async with Client(server) as client:
            tools = await client.list_tools()

        tool = next(t for t in tools if t.name == 'documented_tool')
        assert tool.description == 'This tool has documentation.'
        assert 'value' in tool.inputSchema.get('properties', {})


class TestFastMCPErrorHandling:
    """Test error handling in fastmcp."""

    @pytest.mark.asyncio
    async def test_tool_error_is_raised(self):
        """Test that ToolError is properly raised and caught."""
        server = FastMCP('error-test')

        @server.tool()
        def failing_tool() -> str:
            """Tool that raises an error."""
            raise ToolError('Intentional test error')

        async with Client(server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool('failing_tool', {})

        assert 'Intentional test error' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self):
        """Test calling a tool that doesn't exist."""
        server = FastMCP('nonexistent-test')

        @server.tool()
        def existing_tool() -> str:
            """An existing tool."""
            return 'exists'

        async with Client(server) as client:
            with pytest.raises(ToolError, match='Unknown tool'):
                await client.call_tool('nonexistent_tool', {})


class TestFastMCPProxySupport:
    """Test fastmcp proxy functionality."""

    def test_as_proxy_requires_servers(self):
        """Test that FastMCP.as_proxy requires at least one server."""
        config = {'mcpServers': {}}

        # fastmcp 2.14.3 requires at least one server in the config
        with pytest.raises(ValueError, match='No MCP servers defined'):
            FastMCP.as_proxy(config)

    def test_as_proxy_with_stdio_server(self):
        """Test creating a FastMCP proxy with a stdio server config."""
        config = {
            'mcpServers': {
                'test-server': {
                    'command': 'echo',
                    'args': ['hello'],
                }
            }
        }

        proxy = FastMCP.as_proxy(config)
        assert proxy is not None


class TestOpenHandsMCPIntegration:
    """Test OpenHands MCP components work with fastmcp 2.14.3."""

    @pytest.mark.asyncio
    async def test_mcp_client_tool_to_param(self):
        """Test MCPClientTool can convert to function call format."""
        from openhands.mcp.tool import MCPClientTool

        tool = MCPClientTool(
            name='test_tool',
            description='A test tool',
            inputSchema={'type': 'object', 'properties': {'x': {'type': 'integer'}}},
        )

        param = tool.to_param()
        assert param['type'] == 'function'
        assert param['function']['name'] == 'test_tool'
        assert param['function']['description'] == 'A test tool'


class TestFastMCPConcurrency:
    """Test fastmcp handles concurrent operations correctly."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tool_calls(self):
        """Test multiple concurrent tool calls work correctly."""
        server = FastMCP('concurrency-test')

        @server.tool()
        async def slow_operation(id: int) -> int:
            """Simulate a slow operation."""
            await asyncio.sleep(0.01)
            return id * 10

        async with Client(server) as client:
            # Make multiple concurrent calls
            tasks = [client.call_tool('slow_operation', {'id': i}) for i in range(5)]
            results = await asyncio.gather(*tasks)

        # Verify all results
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result.data == i * 10

    @pytest.mark.asyncio
    async def test_multiple_tool_types(self):
        """Test server with multiple tool types."""
        server = FastMCP('multi-tool-test')

        @server.tool()
        def sync_tool(x: int) -> int:
            """Sync tool."""
            return x + 1

        @server.tool()
        async def async_tool(x: int) -> int:
            """Async tool."""
            await asyncio.sleep(0.001)
            return x * 2

        @server.tool()
        def string_tool(s: str) -> str:
            """String tool."""
            return s.upper()

        async with Client(server) as client:
            r1 = await client.call_tool('sync_tool', {'x': 5})
            r2 = await client.call_tool('async_tool', {'x': 5})
            r3 = await client.call_tool('string_tool', {'s': 'hello'})

        assert r1.data == 6
        assert r2.data == 10
        assert r3.data == 'HELLO'
