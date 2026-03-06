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


class TestMCPClientTool:
    """Test MCPClientTool functionality."""

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

    @pytest.mark.asyncio
    async def test_mcp_client_tool_to_param_with_complex_schema(self):
        """Test MCPClientTool to_param with a complex input schema."""
        from openhands.mcp.tool import MCPClientTool

        complex_schema = {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'The name'},
                'count': {'type': 'integer', 'default': 10},
                'options': {
                    'type': 'object',
                    'properties': {'verbose': {'type': 'boolean'}},
                },
            },
            'required': ['name'],
        }

        tool = MCPClientTool(
            name='complex_tool',
            description='A tool with complex schema',
            inputSchema=complex_schema,
        )

        param = tool.to_param()
        assert param['type'] == 'function'
        assert param['function']['name'] == 'complex_tool'
        assert param['function']['parameters'] == complex_schema
        assert 'required' in param['function']['parameters']


class TestOpenHandsMCPClientIntegration:
    """Test OpenHands MCPClient integration with fastmcp server.

    These tests verify that OpenHands MCPClient can properly connect to
    a fastmcp server, list tools, and call tools through the OpenHands API.
    """

    @pytest.mark.asyncio
    async def test_mcp_client_connects_to_fastmcp_server(self):
        """Test that OpenHands MCPClient can connect to a fastmcp server."""
        from openhands.mcp.client import MCPClient

        # Create a fastmcp server with test tools
        server = FastMCP('openhands-integration-test')

        @server.tool()
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        @server.tool()
        def reverse_string(text: str) -> str:
            """Reverse a string."""
            return text[::-1]

        # Create OpenHands MCPClient
        mcp_client = MCPClient()
        mcp_client.client = Client(server)

        # Initialize and list tools through OpenHands MCPClient
        await mcp_client._initialize_and_list_tools()

        # Verify tools were discovered
        assert len(mcp_client.tools) == 2
        tool_names = [t.name for t in mcp_client.tools]
        assert 'add_numbers' in tool_names
        assert 'reverse_string' in tool_names

        # Verify tool_map is populated
        assert 'add_numbers' in mcp_client.tool_map
        assert 'reverse_string' in mcp_client.tool_map

    @pytest.mark.asyncio
    async def test_mcp_client_lists_tools_with_metadata(self):
        """Test that MCPClient correctly captures tool metadata."""
        from openhands.mcp.client import MCPClient

        server = FastMCP('metadata-integration-test')

        @server.tool()
        def documented_tool(value: int, name: str) -> dict:
            """A well-documented tool that processes data."""
            return {'value': value, 'name': name}

        mcp_client = MCPClient()
        mcp_client.client = Client(server)
        await mcp_client._initialize_and_list_tools()

        # Verify tool metadata
        tool = mcp_client.tool_map['documented_tool']
        assert tool.name == 'documented_tool'
        assert tool.description == 'A well-documented tool that processes data.'
        assert 'value' in tool.inputSchema.get('properties', {})
        assert 'name' in tool.inputSchema.get('properties', {})

        # Verify to_param works correctly
        param = tool.to_param()
        assert param['type'] == 'function'
        assert param['function']['name'] == 'documented_tool'
        assert param['function']['description'] == tool.description

    @pytest.mark.asyncio
    async def test_mcp_client_calls_tool_through_openhands(self):
        """Test calling a tool through OpenHands MCPClient."""
        from openhands.mcp.client import MCPClient

        server = FastMCP('call-tool-integration-test')

        @server.tool()
        def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            return x * y

        @server.tool()
        def greet(name: str) -> str:
            """Generate a greeting."""
            return f'Hello, {name}!'

        mcp_client = MCPClient()
        mcp_client.client = Client(server)
        await mcp_client._initialize_and_list_tools()

        # Call multiply tool through OpenHands MCPClient
        result = await mcp_client.call_tool('multiply', {'x': 7, 'y': 8})
        assert result.content[0].text == '56'

        # Call greet tool
        result = await mcp_client.call_tool('greet', {'name': 'OpenHands'})
        assert result.content[0].text == 'Hello, OpenHands!'

    @pytest.mark.asyncio
    async def test_mcp_client_handles_async_tools(self):
        """Test MCPClient can call async tools on fastmcp server."""
        from openhands.mcp.client import MCPClient

        server = FastMCP('async-tool-integration-test')

        @server.tool()
        async def async_process(data: str) -> str:
            """Process data asynchronously."""
            await asyncio.sleep(0.001)  # Simulate async work
            return f'processed: {data}'

        mcp_client = MCPClient()
        mcp_client.client = Client(server)
        await mcp_client._initialize_and_list_tools()

        result = await mcp_client.call_tool('async_process', {'data': 'test_input'})
        assert result.content[0].text == 'processed: test_input'

    @pytest.mark.asyncio
    async def test_mcp_client_tool_not_found_error(self):
        """Test MCPClient raises error for non-existent tool."""
        from openhands.mcp.client import MCPClient

        server = FastMCP('error-integration-test')

        @server.tool()
        def existing_tool() -> str:
            """An existing tool."""
            return 'exists'

        mcp_client = MCPClient()
        mcp_client.client = Client(server)
        await mcp_client._initialize_and_list_tools()

        # Attempt to call non-existent tool should raise ValueError
        with pytest.raises(ValueError, match='Tool nonexistent_tool not found'):
            await mcp_client.call_tool('nonexistent_tool', {})

    @pytest.mark.asyncio
    async def test_mcp_client_full_workflow(self):
        """Test complete workflow: create server, connect client, list tools, call tool."""
        from openhands.mcp.client import MCPClient
        from openhands.mcp.tool import MCPClientTool

        # Step 1: Create fastmcp server with tools
        server = FastMCP('full-workflow-test')

        @server.tool()
        def calculate(operation: str, a: int, b: int) -> int:
            """Perform a calculation."""
            if operation == 'add':
                return a + b
            elif operation == 'subtract':
                return a - b
            elif operation == 'multiply':
                return a * b
            else:
                raise ValueError(f'Unknown operation: {operation}')

        # Step 2: Connect OpenHands MCPClient
        mcp_client = MCPClient()
        mcp_client.client = Client(server)
        await mcp_client._initialize_and_list_tools()

        # Step 3: List tools through OpenHands
        assert len(mcp_client.tools) == 1
        assert mcp_client.tools[0].name == 'calculate'
        assert isinstance(mcp_client.tools[0], MCPClientTool)

        # Step 4: Convert tool to param format (as used by LLM)
        param = mcp_client.tools[0].to_param()
        assert param['type'] == 'function'
        assert param['function']['name'] == 'calculate'
        assert 'operation' in param['function']['parameters'].get('properties', {})

        # Step 5: Call tool through OpenHands MCPClient
        result = await mcp_client.call_tool(
            'calculate', {'operation': 'add', 'a': 10, 'b': 5}
        )
        assert result.content[0].text == '15'

        result = await mcp_client.call_tool(
            'calculate', {'operation': 'multiply', 'a': 3, 'b': 4}
        )
        assert result.content[0].text == '12'


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
