from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integrations.slack.slack_manager import SlackManager
from integrations.slack.slack_view import SlackNewConversationView
from integrations.utils import infer_repo_from_message
from storage.slack_user import SlackUser

from openhands.integrations.service_types import ProviderTimeoutError, Repository
from openhands.server.user_auth.user_auth import UserAuth


@pytest.fixture
def slack_manager():
    # Mock the token_manager constructor
    slack_manager = SlackManager(token_manager=MagicMock())
    return slack_manager


@pytest.fixture
def mock_slack_user():
    """Create a mock SlackUser."""
    user = SlackUser()
    user.slack_user_id = 'U1234567890'
    user.keycloak_user_id = 'test-user-123'
    user.slack_display_name = 'Test User'
    return user


@pytest.fixture
def mock_user_auth():
    """Create a mock UserAuth."""
    auth = MagicMock(spec=UserAuth)
    auth.get_provider_tokens = AsyncMock(return_value={})
    auth.get_secrets = AsyncMock(return_value=MagicMock(custom_secrets={}))
    return auth


@pytest.fixture
def slack_new_conversation_view(mock_slack_user, mock_user_auth):
    """Create a SlackNewConversationView instance for testing (no repo in message)."""
    return SlackNewConversationView(
        bot_access_token='xoxb-test-token',
        user_msg='Hello OpenHands!',
        slack_user_id='U1234567890',
        slack_to_openhands_user=mock_slack_user,
        saas_user_auth=mock_user_auth,
        channel_id='C1234567890',
        message_ts='1234567890.123456',
        thread_ts=None,
        selected_repo=None,
        should_extract=True,
        send_summary_instruction=True,
        conversation_id='',
        team_id='T1234567890',
        v1_enabled=False,
    )


@pytest.fixture
def slack_new_conversation_view_with_repo(mock_slack_user, mock_user_auth):
    """Create a SlackNewConversationView instance with a repo in the message."""
    return SlackNewConversationView(
        bot_access_token='xoxb-test-token',
        user_msg='Please work on OpenHands/OpenHands repo',
        slack_user_id='U1234567890',
        slack_to_openhands_user=mock_slack_user,
        saas_user_auth=mock_user_auth,
        channel_id='C1234567890',
        message_ts='1234567890.123456',
        thread_ts=None,
        selected_repo=None,
        should_extract=True,
        send_summary_instruction=True,
        conversation_id='',
        team_id='T1234567890',
        v1_enabled=False,
    )


@pytest.fixture
def slack_new_conversation_view_with_multiple_repos(mock_slack_user, mock_user_auth):
    """Create a SlackNewConversationView instance with multiple repos in the message."""
    return SlackNewConversationView(
        bot_access_token='xoxb-test-token',
        user_msg='Please work on OpenHands/OpenHands and OpenHands/openhands-resolver repos',
        slack_user_id='U1234567890',
        slack_to_openhands_user=mock_slack_user,
        saas_user_auth=mock_user_auth,
        channel_id='C1234567890',
        message_ts='1234567890.123456',
        thread_ts=None,
        selected_repo=None,
        should_extract=True,
        send_summary_instruction=True,
        conversation_id='',
        team_id='T1234567890',
        v1_enabled=False,
    )


@pytest.mark.parametrize(
    'message,expected',
    [
        ('OpenHands/Openhands', ['OpenHands/Openhands']),
        ('use hello world', []),
        (
            'work on OpenHands/OpenHands and OpenHands/resolver',
            ['OpenHands/OpenHands', 'OpenHands/resolver'],
        ),
    ],
)
def test_infer_repo_from_message(message, expected):
    # Test the utility function
    result = infer_repo_from_message(message)
    assert result == expected


class TestRepoQueryTimeoutHandling:
    """Test timeout handling when fetching repositories for Slack integration."""

    @patch.object(SlackManager, 'send_message', new_callable=AsyncMock)
    @patch.object(SlackManager, '_get_repositories', new_callable=AsyncMock)
    async def test_timeout_sends_user_friendly_message(
        self,
        mock_get_repositories,
        mock_send_message,
        slack_manager,
        slack_new_conversation_view,
    ):
        """Test that when repository fetching times out, a user-friendly message is sent."""
        # Setup: _get_repositories raises ProviderTimeoutError
        # Note: This test uses a view with no repo in message, so it goes to _get_repositories
        mock_get_repositories.side_effect = ProviderTimeoutError(
            'github API request timed out: ConnectTimeout'
        )

        # Execute
        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view
        )

        # Verify: should return False (job not started)
        assert result is False

        # Verify: send_message was called with the timeout message
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args

        # Check the message content
        message = call_args[0][0]
        assert 'timed out' in message
        assert 'repository name' in message
        assert 'owner/repo-name' in message

        # Check it was sent as ephemeral
        assert call_args[1]['ephemeral'] is True

    @patch.object(SlackManager, 'send_message', new_callable=AsyncMock)
    @patch.object(SlackManager, '_get_repositories', new_callable=AsyncMock)
    async def test_successful_repo_fetch_does_not_send_timeout_message(
        self,
        mock_get_repositories,
        mock_send_message,
        slack_manager,
        slack_new_conversation_view,
    ):
        """Test that successful repo fetch shows repo selector, not timeout message."""
        # Setup: _get_repositories returns empty list (no repos, but no timeout)
        # Note: This test uses a view with no repo in message, so it goes to _get_repositories
        mock_get_repositories.return_value = []

        # Execute
        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view
        )

        # Verify: should return False (no repo selected yet)
        assert result is False

        # Verify: send_message was called (for repo selector)
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args

        # Check the message is NOT the timeout message
        message = call_args[0][0]
        assert 'timed out' not in str(message)
        # Should be the repo selection form
        assert isinstance(message, dict)
        assert message.get('text') == 'Choose a Repository:'


class TestRepoSearchBehavior:
    """Test the new repo search behavior when user specifies a repo in their message."""

    @patch.object(SlackManager, 'send_message', new_callable=AsyncMock)
    async def test_multiple_repos_in_message_asks_for_clarification(
        self,
        mock_send_message,
        slack_manager,
        slack_new_conversation_view_with_multiple_repos,
    ):
        """Test that when multiple repos are mentioned in the message, user is asked to clarify."""
        # Execute
        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view_with_multiple_repos
        )

        # Verify: should return False (need clarification)
        assert result is False

        # Verify: send_message was called with clarification message
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args

        # Check the message content
        message = call_args[0][0]
        assert 'multiple repositories mentioned' in message.lower()
        assert 'OpenHands/OpenHands' in message
        assert 'OpenHands/openhands-resolver' in message

        # Check it was sent as ephemeral
        assert call_args[1]['ephemeral'] is True

    @patch.object(SlackManager, 'send_message', new_callable=AsyncMock)
    @patch.object(SlackManager, '_verify_repository', new_callable=AsyncMock)
    async def test_repo_found_proceeds_with_job(
        self,
        mock_verify_repository,
        mock_send_message,
        slack_manager,
        slack_new_conversation_view_with_repo,
    ):
        """Test that when the specified repo is found, the job proceeds."""
        # Setup: _verify_repository returns the repository
        mock_verify_repository.return_value = Repository(
            id='123', full_name='OpenHands/OpenHands'
        )

        # Execute
        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view_with_repo
        )

        # Verify: should return True (job can proceed)
        assert result is True

        # Verify: selected_repo was set
        assert (
            slack_new_conversation_view_with_repo.selected_repo
            == 'OpenHands/OpenHands'
        )

        # Verify: no message was sent (job proceeds directly)
        mock_send_message.assert_not_called()

    @patch.object(SlackManager, 'send_message', new_callable=AsyncMock)
    @patch.object(SlackManager, '_get_repositories', new_callable=AsyncMock)
    @patch.object(SlackManager, '_verify_repository', new_callable=AsyncMock)
    async def test_repo_not_found_falls_back_to_dropdown(
        self,
        mock_verify_repository,
        mock_get_repositories,
        mock_send_message,
        slack_manager,
        slack_new_conversation_view_with_repo,
    ):
        """Test that when repo is not found, it falls back to showing the repo dropdown."""
        # Setup: _verify_repository returns None (repo not found)
        mock_verify_repository.return_value = None
        mock_get_repositories.return_value = [
            Repository(id='789', full_name='SomeOrg/SomeRepo'),
        ]

        # Execute
        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view_with_repo
        )

        # Verify: should return False (showing dropdown)
        assert result is False

        # Verify: _get_repositories was called (fallback to loading all repos)
        mock_get_repositories.assert_called_once()

        # Verify: send_message was called with repo selector
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args

        # Check the message is the repo selection form
        message = call_args[0][0]
        assert isinstance(message, dict)
        assert message.get('text') == 'Choose a Repository:'

        # Check it was sent as ephemeral
        assert call_args[1]['ephemeral'] is True

    @patch.object(SlackManager, 'send_message', new_callable=AsyncMock)
    @patch.object(SlackManager, '_verify_repository', new_callable=AsyncMock)
    async def test_repo_verify_timeout_sends_error_message(
        self,
        mock_verify_repository,
        mock_send_message,
        slack_manager,
        slack_new_conversation_view_with_repo,
    ):
        """Test that when repo verification times out, user is notified."""
        # Setup: _verify_repository raises ProviderTimeoutError
        mock_verify_repository.side_effect = ProviderTimeoutError(
            'github API request timed out'
        )

        # Execute
        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view_with_repo
        )

        # Verify: should return False
        assert result is False

        # Verify: send_message was called with timeout message
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args

        # Check the message content
        message = call_args[0][0]
        assert 'timed out' in message.lower()
        assert 'OpenHands/OpenHands' in message

        # Check it was sent as ephemeral
        assert call_args[1]['ephemeral'] is True
