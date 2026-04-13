"""Unit tests for git and security functionality in AppConversationServiceBase.

This module tests the git-related functionality, specifically the clone_or_init_git_repo method
and the recent bug fixes for git checkout operations.
"""

import subprocess
from pathlib import Path
from types import MethodType
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from openhands.app_server.app_conversation.app_conversation_service_base import (
    AppConversationServiceBase,
)
from openhands.app_server.sandbox.sandbox_models import SandboxInfo
from openhands.app_server.user.user_context import UserContext
from openhands.sdk.skills import Skill


class MockUserInfo:
    """Mock class for UserInfo to simulate user settings."""

    def __init__(
        self, git_user_name: str | None = None, git_user_email: str | None = None
    ):
        self.git_user_name = git_user_name
        self.git_user_email = git_user_email


class MockCommandResult:
    """Mock class for command execution result."""

    def __init__(self, exit_code: int = 0, stderr: str = ''):
        self.exit_code = exit_code
        self.stderr = stderr


class MockWorkspace:
    """Mock class for AsyncRemoteWorkspace."""

    def __init__(self, working_dir: str = '/workspace'):
        self.working_dir = working_dir
        self.execute_command = AsyncMock(return_value=MockCommandResult())


class MockAppConversationServiceBase:
    """Mock class to test git functionality without complex dependencies."""

    def __init__(self):
        self.logger = MagicMock()

    async def clone_or_init_git_repo(
        self,
        workspace_path: str,
        repo_url: str,
        branch: str = 'main',
        timeout: int = 300,
    ) -> bool:
        """Clone or initialize a git repository.

        This is a simplified version of the actual method for testing purposes.
        """
        try:
            # Try to clone the repository
            clone_result = subprocess.run(
                ['git', 'clone', '--branch', branch, repo_url, workspace_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if clone_result.returncode == 0:
                self.logger.info(
                    f'Successfully cloned repository {repo_url} to {workspace_path}'
                )
                return True

            # If clone fails, try to checkout the branch
            checkout_result = subprocess.run(
                ['git', 'checkout', branch],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if checkout_result.returncode == 0:
                self.logger.info(f'Successfully checked out branch {branch}')
                return True
            else:
                self.logger.error(
                    f'Failed to checkout branch {branch}: {checkout_result.stderr}'
                )
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f'Git operation timed out after {timeout} seconds')
            return False
        except Exception as e:
            self.logger.error(f'Git operation failed: {str(e)}')
            return False


@pytest.fixture
def service():
    """Create a mock service instance for testing."""
    return MockAppConversationServiceBase()


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_successful_clone(service):
    """Test successful git clone operation."""
    with patch('subprocess.run') as mock_run:
        # Mock successful clone
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='Cloning...')

        result = await service.clone_or_init_git_repo(
            workspace_path='/tmp/test_repo',
            repo_url='https://github.com/test/repo.git',
            branch='main',
            timeout=300,
        )

        assert result is True
        mock_run.assert_called_once_with(
            [
                'git',
                'clone',
                '--branch',
                'main',
                'https://github.com/test/repo.git',
                '/tmp/test_repo',
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        service.logger.info.assert_called_with(
            'Successfully cloned repository https://github.com/test/repo.git to /tmp/test_repo'
        )


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_clone_fails_checkout_succeeds(service):
    """Test git clone fails but checkout succeeds."""
    with patch('subprocess.run') as mock_run:
        # Mock clone failure, then checkout success
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='Clone failed', stdout=''),  # Clone fails
            MagicMock(
                returncode=0, stderr='', stdout='Switched to branch'
            ),  # Checkout succeeds
        ]

        result = await service.clone_or_init_git_repo(
            workspace_path='/tmp/test_repo',
            repo_url='https://github.com/test/repo.git',
            branch='feature-branch',
            timeout=300,
        )

        assert result is True
        assert mock_run.call_count == 2

        # Check clone call
        mock_run.assert_any_call(
            [
                'git',
                'clone',
                '--branch',
                'feature-branch',
                'https://github.com/test/repo.git',
                '/tmp/test_repo',
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Check checkout call
        mock_run.assert_any_call(
            ['git', 'checkout', 'feature-branch'],
            cwd='/tmp/test_repo',
            capture_output=True,
            text=True,
            timeout=300,
        )

        service.logger.info.assert_called_with(
            'Successfully checked out branch feature-branch'
        )


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_both_operations_fail(service):
    """Test both git clone and checkout operations fail."""
    with patch('subprocess.run') as mock_run:
        # Mock both operations failing
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='Clone failed', stdout=''),  # Clone fails
            MagicMock(
                returncode=1, stderr='Checkout failed', stdout=''
            ),  # Checkout fails
        ]

        result = await service.clone_or_init_git_repo(
            workspace_path='/tmp/test_repo',
            repo_url='https://github.com/test/repo.git',
            branch='nonexistent-branch',
            timeout=300,
        )

        assert result is False
        assert mock_run.call_count == 2
        service.logger.error.assert_called_with(
            'Failed to checkout branch nonexistent-branch: Checkout failed'
        )


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_timeout(service):
    """Test git operation timeout."""
    with patch('subprocess.run') as mock_run:
        # Mock timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['git', 'clone'], timeout=300
        )

        result = await service.clone_or_init_git_repo(
            workspace_path='/tmp/test_repo',
            repo_url='https://github.com/test/repo.git',
            branch='main',
            timeout=300,
        )

        assert result is False
        service.logger.error.assert_called_with(
            'Git operation timed out after 300 seconds'
        )


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_exception(service):
    """Test git operation with unexpected exception."""
    with patch('subprocess.run') as mock_run:
        # Mock unexpected exception
        mock_run.side_effect = Exception('Unexpected error')

        result = await service.clone_or_init_git_repo(
            workspace_path='/tmp/test_repo',
            repo_url='https://github.com/test/repo.git',
            branch='main',
            timeout=300,
        )

        assert result is False
        service.logger.error.assert_called_with(
            'Git operation failed: Unexpected error'
        )


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_custom_timeout(service):
    """Test git operation with custom timeout."""
    with patch('subprocess.run') as mock_run:
        # Mock successful clone with custom timeout
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='Cloning...')

        result = await service.clone_or_init_git_repo(
            workspace_path='/tmp/test_repo',
            repo_url='https://github.com/test/repo.git',
            branch='main',
            timeout=600,  # Custom timeout
        )

        assert result is True
        mock_run.assert_called_once_with(
            [
                'git',
                'clone',
                '--branch',
                'main',
                'https://github.com/test/repo.git',
                '/tmp/test_repo',
            ],
            capture_output=True,
            text=True,
            timeout=600,  # Verify custom timeout is used
        )


# =============================================================================
# Tests for _configure_git_user_settings
# =============================================================================


def _create_service_with_mock_user_context(
    user_info: MockUserInfo, bind_methods: tuple[str, ...] | None = None
) -> tuple:
    """Create a mock service with selected real methods bound for testing.

    Uses MagicMock for the service but binds the real method for testing.

    Returns a tuple of (service, mock_user_context) for testing.
    """
    mock_user_context = MagicMock()
    mock_user_context.get_user_info = AsyncMock(return_value=user_info)

    # Create a simple mock service and set required attribute
    service = MagicMock()
    service.user_context = mock_user_context
    methods_to_bind = ['_configure_git_user_settings']
    if bind_methods:
        methods_to_bind.extend(bind_methods)
        # Remove potential duplicates while keeping order
        methods_to_bind = list(dict.fromkeys(methods_to_bind))

    # Bind actual methods from the real class to test implementations directly
    for method_name in methods_to_bind:
        real_method = getattr(AppConversationServiceBase, method_name)
        setattr(service, method_name, MethodType(real_method, service))

    return service, mock_user_context


@pytest.fixture
def mock_workspace():
    """Create a mock workspace instance for testing."""
    return MockWorkspace(working_dir='/workspace/project')


@pytest.mark.asyncio
async def test_clone_or_init_git_repo_quotes_selected_branch_before_checkout(
    mock_workspace,
):
    user_info = MockUserInfo()
    service, mock_user_context = _create_service_with_mock_user_context(
        user_info, bind_methods=('clone_or_init_git_repo',)
    )
    service.init_git_in_empty_workspace = True
    mock_user_context.get_authenticated_git_url = AsyncMock(
        return_value='https://github.com/owner/repo.git'
    )

    task = Mock()
    task.request = Mock(
        selected_repository='owner/repo',
        selected_branch='feature>tmp',
    )

    await service.clone_or_init_git_repo(task, mock_workspace)

    mock_workspace.execute_command.assert_any_call(
        "git checkout 'feature>tmp'",
        Path(mock_workspace.working_dir) / 'repo',
    )


@pytest.mark.asyncio
async def test_configure_git_user_settings_both_name_and_email(mock_workspace):
    """Test configuring both git user name and email."""
    user_info = MockUserInfo(
        git_user_name='Test User', git_user_email='test@example.com'
    )
    service, mock_user_context = _create_service_with_mock_user_context(user_info)

    await service._configure_git_user_settings(mock_workspace)

    # Verify get_user_info was called
    mock_user_context.get_user_info.assert_called_once()

    # Verify both git config commands were executed
    assert mock_workspace.execute_command.call_count == 2

    # Check git config user.name call
    mock_workspace.execute_command.assert_any_call(
        'git config --global user.name "Test User"', '/workspace/project'
    )

    # Check git config user.email call
    mock_workspace.execute_command.assert_any_call(
        'git config --global user.email "test@example.com"', '/workspace/project'
    )


@pytest.mark.asyncio
async def test_configure_git_user_settings_only_name(mock_workspace):
    """Test configuring only git user name."""
    user_info = MockUserInfo(git_user_name='Test User', git_user_email=None)
    service, _ = _create_service_with_mock_user_context(user_info)

    await service._configure_git_user_settings(mock_workspace)

    # Verify only user.name was configured
    assert mock_workspace.execute_command.call_count == 1
    mock_workspace.execute_command.assert_called_once_with(
        'git config --global user.name "Test User"', '/workspace/project'
    )


@pytest.mark.asyncio
async def test_configure_git_user_settings_only_email(mock_workspace):
    """Test configuring only git user email."""
    user_info = MockUserInfo(git_user_name=None, git_user_email='test@example.com')
    service, _ = _create_service_with_mock_user_context(user_info)

    await service._configure_git_user_settings(mock_workspace)

    # Verify only user.email was configured
    assert mock_workspace.execute_command.call_count == 1
    mock_workspace.execute_command.assert_called_once_with(
        'git config --global user.email "test@example.com"', '/workspace/project'
    )


@pytest.mark.asyncio
async def test_configure_git_user_settings_neither_set(mock_workspace):
    """Test when neither git user name nor email is set."""
    user_info = MockUserInfo(git_user_name=None, git_user_email=None)
    service, _ = _create_service_with_mock_user_context(user_info)

    await service._configure_git_user_settings(mock_workspace)

    # Verify no git config commands were executed
    mock_workspace.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_configure_git_user_settings_empty_strings(mock_workspace):
    """Test when git user name and email are empty strings."""
    user_info = MockUserInfo(git_user_name='', git_user_email='')
    service, _ = _create_service_with_mock_user_context(user_info)

    await service._configure_git_user_settings(mock_workspace)

    # Empty strings are falsy, so no commands should be executed
    mock_workspace.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_configure_git_user_settings_get_user_info_fails(mock_workspace):
    """Test handling of exception when get_user_info fails."""
    user_info = MockUserInfo()
    service, mock_user_context = _create_service_with_mock_user_context(user_info)
    mock_user_context.get_user_info = AsyncMock(
        side_effect=Exception('User info error')
    )

    # Should not raise exception, just log warning
    await service._configure_git_user_settings(mock_workspace)

    # Verify no git config commands were executed
    mock_workspace.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_configure_git_user_settings_name_command_fails(mock_workspace):
    """Test handling when git config user.name command fails."""
    user_info = MockUserInfo(
        git_user_name='Test User', git_user_email='test@example.com'
    )
    service, _ = _create_service_with_mock_user_context(user_info)

    # Make the first command fail (user.name), second succeed (user.email)
    mock_workspace.execute_command = AsyncMock(
        side_effect=[
            MockCommandResult(exit_code=1, stderr='Permission denied'),
            MockCommandResult(exit_code=0),
        ]
    )

    # Should not raise exception
    await service._configure_git_user_settings(mock_workspace)

    # Verify both commands were still attempted
    assert mock_workspace.execute_command.call_count == 2


@pytest.mark.asyncio
async def test_configure_git_user_settings_email_command_fails(mock_workspace):
    """Test handling when git config user.email command fails."""
    user_info = MockUserInfo(
        git_user_name='Test User', git_user_email='test@example.com'
    )
    service, _ = _create_service_with_mock_user_context(user_info)

    # Make the first command succeed (user.name), second fail (user.email)
    mock_workspace.execute_command = AsyncMock(
        side_effect=[
            MockCommandResult(exit_code=0),
            MockCommandResult(exit_code=1, stderr='Permission denied'),
        ]
    )

    # Should not raise exception
    await service._configure_git_user_settings(mock_workspace)

    # Verify both commands were still attempted
    assert mock_workspace.execute_command.call_count == 2


@pytest.mark.asyncio
async def test_configure_git_user_settings_special_characters_in_name(mock_workspace):
    """Test git user name with special characters."""
    user_info = MockUserInfo(
        git_user_name="Test O'Brien", git_user_email='test@example.com'
    )
    service, _ = _create_service_with_mock_user_context(user_info)

    await service._configure_git_user_settings(mock_workspace)

    # Verify the name is passed with special characters
    mock_workspace.execute_command.assert_any_call(
        'git config --global user.name "Test O\'Brien"', '/workspace/project'
    )


# =============================================================================
# Tests for load_and_merge_all_skills (updated to use agent-server)
# =============================================================================


class TestMergeSkills:
    """Test _merge_skills method."""

    def test_merges_skills_with_no_duplicates(self):
        """Test merging skill lists with no duplicate names."""
        # Arrange
        mock_user_context = Mock(spec=UserContext)
        with patch.object(AppConversationServiceBase, '__abstractmethods__', set()):
            service = AppConversationServiceBase(
                init_git_in_empty_workspace=True, user_context=mock_user_context
            )

            skill1 = Mock(spec=Skill)
            skill1.name = 'skill1'
            skill2 = Mock(spec=Skill)
            skill2.name = 'skill2'
            skill3 = Mock(spec=Skill)
            skill3.name = 'skill3'

            skill_lists = [[skill1], [skill2], [skill3]]

            # Act
            result = service._merge_skills(skill_lists)

            # Assert
            assert len(result) == 3
            names = {s.name for s in result}
            assert names == {'skill1', 'skill2', 'skill3'}

    def test_merges_skills_with_duplicates_later_wins(self):
        """Test that later skill lists override earlier ones for duplicate names."""
        # Arrange
        mock_user_context = Mock(spec=UserContext)
        with patch.object(AppConversationServiceBase, '__abstractmethods__', set()):
            service = AppConversationServiceBase(
                init_git_in_empty_workspace=True, user_context=mock_user_context
            )

            skill1_v1 = Mock(spec=Skill)
            skill1_v1.name = 'skill1'
            skill1_v1.version = 'v1'

            skill1_v2 = Mock(spec=Skill)
            skill1_v2.name = 'skill1'
            skill1_v2.version = 'v2'

            skill2 = Mock(spec=Skill)
            skill2.name = 'skill2'

            skill_lists = [[skill1_v1], [skill1_v2, skill2]]

            # Act
            result = service._merge_skills(skill_lists)

            # Assert
            assert len(result) == 2
            skill1_result = next(s for s in result if s.name == 'skill1')
            assert skill1_result.version == 'v2'


class TestLoadAndMergeAllSkills:
    """Test load_and_merge_all_skills method (updated to use agent-server)."""

    @pytest.mark.asyncio
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.load_skills_from_agent_server'
    )
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.build_org_config'
    )
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.build_sandbox_config'
    )
    async def test_loads_skills_successfully(
        self,
        mock_build_sandbox_config,
        mock_build_org_config,
        mock_load_skills,
    ):
        """Test successfully loading skills from agent-server."""
        # Arrange
        mock_user_context = Mock(spec=UserContext)
        with patch.object(AppConversationServiceBase, '__abstractmethods__', set()):
            service = AppConversationServiceBase(
                init_git_in_empty_workspace=True, user_context=mock_user_context
            )

            mock_workspace = AsyncMock()
            mock_workspace.working_dir = '/workspace'

            from openhands.app_server.sandbox.sandbox_models import ExposedUrl

            sandbox = Mock(spec=SandboxInfo)
            exposed_url = ExposedUrl(
                name='AGENT_SERVER', url='http://localhost:8000', port=8000
            )
            sandbox.exposed_urls = [exposed_url]
            sandbox.session_api_key = 'test-api-key'

            skill1 = Mock(spec=Skill)
            skill1.name = 'skill1'
            skill2 = Mock(spec=Skill)
            skill2.name = 'skill2'

            mock_load_skills.return_value = [skill1, skill2]
            mock_build_org_config.return_value = {'repository': 'owner/repo'}
            mock_build_sandbox_config.return_value = {'exposed_urls': []}

            # Act
            result = await service.load_and_merge_all_skills(
                sandbox, 'owner/repo', '/workspace/repo', 'http://localhost:8000'
            )

            # Assert
            assert len(result) == 2
            assert result[0].name == 'skill1'
            assert result[1].name == 'skill2'
            mock_load_skills.assert_called_once()
            call_kwargs = mock_load_skills.call_args[1]
            assert call_kwargs['agent_server_url'] == 'http://localhost:8000'
            assert call_kwargs['session_api_key'] == 'test-api-key'
            assert call_kwargs['project_dir'] == '/workspace/repo'

    @pytest.mark.asyncio
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.load_skills_from_agent_server'
    )
    async def test_returns_empty_list_when_no_agent_server_url(self, mock_load_skills):
        """Test returns empty list when agent-server URL is not available."""
        # Arrange
        mock_user_context = Mock(spec=UserContext)
        with patch.object(AppConversationServiceBase, '__abstractmethods__', set()):
            service = AppConversationServiceBase(
                init_git_in_empty_workspace=True, user_context=mock_user_context
            )

            AsyncMock()
            from openhands.app_server.sandbox.sandbox_models import ExposedUrl

            sandbox = Mock(spec=SandboxInfo)
            exposed_url = ExposedUrl(
                name='VSCODE', url='http://localhost:8080', port=8080
            )
            sandbox.exposed_urls = [exposed_url]

            # Act - pass empty string to simulate no agent server URL
            # This should still call load_skills_from_agent_server but it will fail
            result = await service.load_and_merge_all_skills(
                sandbox, 'owner/repo', '/workspace/repo', ''
            )

            # Assert - should return empty list when agent_server_url is empty
            assert result == []

    @pytest.mark.asyncio
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.load_skills_from_agent_server'
    )
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.build_org_config'
    )
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.build_sandbox_config'
    )
    async def test_uses_project_dir_when_no_repository(
        self,
        mock_build_sandbox_config,
        mock_build_org_config,
        mock_load_skills,
    ):
        """Test uses project_dir directly when no repository is selected."""
        # Arrange
        mock_user_context = Mock(spec=UserContext)
        with patch.object(AppConversationServiceBase, '__abstractmethods__', set()):
            service = AppConversationServiceBase(
                init_git_in_empty_workspace=True, user_context=mock_user_context
            )

            AsyncMock()
            from openhands.app_server.sandbox.sandbox_models import ExposedUrl

            sandbox = Mock(spec=SandboxInfo)
            exposed_url = ExposedUrl(
                name='AGENT_SERVER', url='http://localhost:8000', port=8000
            )
            sandbox.exposed_urls = [exposed_url]
            sandbox.session_api_key = 'test-key'

            mock_load_skills.return_value = []
            mock_build_org_config.return_value = None
            mock_build_sandbox_config.return_value = None

            # Act
            await service.load_and_merge_all_skills(
                sandbox, None, '/workspace', 'http://localhost:8000'
            )

            # Assert
            call_kwargs = mock_load_skills.call_args[1]
            assert call_kwargs['project_dir'] == '/workspace'

    @pytest.mark.asyncio
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.load_skills_from_agent_server'
    )
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.build_org_config'
    )
    @patch(
        'openhands.app_server.app_conversation.app_conversation_service_base.build_sandbox_config'
    )
    async def test_handles_exception_gracefully(
        self,
        mock_build_sandbox_config,
        mock_build_org_config,
        mock_load_skills,
    ):
        """Test handles exceptions during skill loading."""
        # Arrange
        mock_user_context = Mock(spec=UserContext)
        with patch.object(AppConversationServiceBase, '__abstractmethods__', set()):
            service = AppConversationServiceBase(
                init_git_in_empty_workspace=True, user_context=mock_user_context
            )

            AsyncMock()
            from openhands.app_server.sandbox.sandbox_models import ExposedUrl

            sandbox = Mock(spec=SandboxInfo)
            exposed_url = ExposedUrl(
                name='AGENT_SERVER', url='http://localhost:8000', port=8000
            )
            sandbox.exposed_urls = [exposed_url]
            sandbox.session_api_key = 'test-key'

            mock_load_skills.side_effect = Exception('Network error')

            # Act
            result = await service.load_and_merge_all_skills(
                sandbox, 'owner/repo', '/workspace/repo', 'http://localhost:8000'
            )

            # Assert
            assert result == []
