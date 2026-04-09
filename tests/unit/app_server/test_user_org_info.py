"""Unit tests for organization info fields in GET /api/v1/users/me endpoint.

Tests:
- UserInfo model with org fields
- AuthUserContext.get_user_info() with org info
- get_org_info() method in UserAuth base class
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestUserInfoOrgFields:
    """Test suite for UserInfo model org fields."""

    def test_user_info_with_all_org_fields(self):
        """UserInfo should accept all org-related fields."""
        from openhands.app_server.user.user_models import UserInfo

        user_info = UserInfo(
            id='user-123',
            org_id='org-456',
            org_name='Test Organization',
            role='admin',
            permissions=['read', 'write', 'delete'],
        )

        assert user_info.id == 'user-123'
        assert user_info.org_id == 'org-456'
        assert user_info.org_name == 'Test Organization'
        assert user_info.role == 'admin'
        assert user_info.permissions == ['read', 'write', 'delete']

    def test_user_info_without_org_fields(self):
        """UserInfo should work without org fields (OSS mode)."""
        from openhands.app_server.user.user_models import UserInfo

        user_info = UserInfo(id='user-123')

        assert user_info.id == 'user-123'
        assert user_info.org_id is None
        assert user_info.org_name is None
        assert user_info.role is None
        assert user_info.permissions is None

    def test_user_info_with_partial_org_fields(self):
        """UserInfo should handle partial org fields (e.g., role is None)."""
        from openhands.app_server.user.user_models import UserInfo

        user_info = UserInfo(
            id='user-123',
            org_id='org-456',
            org_name='Test Organization',
            role=None,
            permissions=[],
        )

        assert user_info.org_id == 'org-456'
        assert user_info.org_name == 'Test Organization'
        assert user_info.role is None
        assert user_info.permissions == []

    def test_user_info_model_dump_includes_org_fields(self):
        """UserInfo model_dump should include org fields."""
        from openhands.app_server.user.user_models import UserInfo

        user_info = UserInfo(
            id='user-123',
            org_id='org-456',
            org_name='Test Organization',
            role='member',
            permissions=['read'],
        )

        data = user_info.model_dump()
        assert data['org_id'] == 'org-456'
        assert data['org_name'] == 'Test Organization'
        assert data['role'] == 'member'
        assert data['permissions'] == ['read']


class TestUserAuthGetOrgInfo:
    """Test suite for UserAuth.get_org_info() base implementation."""

    @pytest.mark.asyncio
    async def test_base_user_auth_returns_none(self):
        """Base UserAuth.get_org_info() should return None (OSS mode)."""
        from openhands.server.user_auth.user_auth import UserAuth

        # Create a minimal mock that inherits from UserAuth
        class MockUserAuth(UserAuth):
            _settings = None

            async def get_user_id(self):
                return 'user-123'

            async def get_user_email(self):
                return 'test@example.com'

            async def get_access_token(self):
                return None

            async def get_provider_tokens(self):
                return None

            async def get_user_settings_store(self):
                return MagicMock()

            async def get_secrets_store(self):
                return MagicMock()

            async def get_secrets(self):
                return None

            async def get_mcp_api_key(self):
                return None

            @classmethod
            async def get_instance(cls, request):
                return cls()

            @classmethod
            async def get_for_user(cls, user_id):
                return cls()

        user_auth = MockUserAuth()
        org_info = await user_auth.get_org_info()

        assert org_info is None


class TestAuthUserContextOrgInfo:
    """Test suite for AuthUserContext.get_user_info() with org info."""

    @pytest.fixture
    def mock_user_auth(self):
        """Create a mock UserAuth instance."""
        from pydantic import SecretStr

        mock = AsyncMock()
        mock.get_user_id = AsyncMock(return_value='user-123')
        mock.get_user_settings = AsyncMock(
            return_value=MagicMock(
                model_dump=MagicMock(
                    return_value={
                        'llm_model': 'test-model',
                        'llm_api_key': SecretStr('test-key'),
                    }
                )
            )
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_user_info_includes_org_info_when_available(self, mock_user_auth):
        """get_user_info should include org fields when get_org_info returns data."""
        from openhands.app_server.user.auth_user_context import AuthUserContext

        mock_user_auth.get_org_info = AsyncMock(
            return_value={
                'org_id': 'org-456',
                'org_name': 'Test Organization',
                'role': 'admin',
                'permissions': ['read', 'write', 'delete'],
            }
        )

        context = AuthUserContext(user_auth=mock_user_auth)
        user_info = await context.get_user_info()

        assert user_info.id == 'user-123'
        assert user_info.org_id == 'org-456'
        assert user_info.org_name == 'Test Organization'
        assert user_info.role == 'admin'
        assert user_info.permissions == ['read', 'write', 'delete']

    @pytest.mark.asyncio
    async def test_get_user_info_without_org_info(self, mock_user_auth):
        """get_user_info should work without org info (OSS mode)."""
        from openhands.app_server.user.auth_user_context import AuthUserContext

        mock_user_auth.get_org_info = AsyncMock(return_value=None)

        context = AuthUserContext(user_auth=mock_user_auth)
        user_info = await context.get_user_info()

        assert user_info.id == 'user-123'
        assert user_info.org_id is None
        assert user_info.org_name is None
        assert user_info.role is None
        assert user_info.permissions is None

    @pytest.mark.asyncio
    async def test_get_user_info_caches_result(self, mock_user_auth):
        """get_user_info should cache the result after first call."""
        from openhands.app_server.user.auth_user_context import AuthUserContext

        mock_user_auth.get_org_info = AsyncMock(
            return_value={
                'org_id': 'org-456',
                'org_name': 'Test Organization',
                'role': 'admin',
                'permissions': ['read'],
            }
        )

        context = AuthUserContext(user_auth=mock_user_auth)

        # First call
        user_info1 = await context.get_user_info()
        # Second call
        user_info2 = await context.get_user_info()

        # Should return the same cached instance
        assert user_info1 is user_info2
        # get_org_info should only be called once due to caching
        mock_user_auth.get_org_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_info_handles_partial_org_info(self, mock_user_auth):
        """get_user_info should handle partial org info (e.g., role is None)."""
        from openhands.app_server.user.auth_user_context import AuthUserContext

        mock_user_auth.get_org_info = AsyncMock(
            return_value={
                'org_id': 'org-456',
                'org_name': 'Test Organization',
                'role': None,
                'permissions': [],
            }
        )

        context = AuthUserContext(user_auth=mock_user_auth)
        user_info = await context.get_user_info()

        assert user_info.org_id == 'org-456'
        assert user_info.org_name == 'Test Organization'
        assert user_info.role is None
        assert user_info.permissions == []


class TestGetCurrentUserEndpointOrgFields:
    """Test suite for GET /api/v1/users/me endpoint org fields."""

    @pytest.fixture
    def mock_user_context(self):
        """Create a mock user context."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_endpoint_returns_org_fields(self, mock_user_context):
        """GET /users/me should return org fields in response."""
        from openhands.app_server.user.user_models import UserInfo
        from openhands.app_server.user.user_router import get_current_user

        user_info = UserInfo(
            id='user-123',
            llm_model='test-model',
            org_id='org-456',
            org_name='Test Organization',
            role='member',
            permissions=['read', 'write'],
        )
        mock_user_context.get_user_info = AsyncMock(return_value=user_info)

        result = await get_current_user(user_context=mock_user_context)

        assert result.id == 'user-123'
        assert result.org_id == 'org-456'
        assert result.org_name == 'Test Organization'
        assert result.role == 'member'
        assert result.permissions == ['read', 'write']

    @pytest.mark.asyncio
    async def test_endpoint_returns_null_org_fields_in_oss_mode(
        self, mock_user_context
    ):
        """GET /users/me should return null org fields in OSS mode."""
        from openhands.app_server.user.user_models import UserInfo
        from openhands.app_server.user.user_router import get_current_user

        user_info = UserInfo(
            id='user-123',
            llm_model='test-model',
            # No org fields set (OSS mode)
        )
        mock_user_context.get_user_info = AsyncMock(return_value=user_info)

        result = await get_current_user(user_context=mock_user_context)

        assert result.id == 'user-123'
        assert result.org_id is None
        assert result.org_name is None
        assert result.role is None
        assert result.permissions is None
