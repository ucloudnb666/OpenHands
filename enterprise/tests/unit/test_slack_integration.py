from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integrations.slack.slack_manager import SlackManager
from integrations.slack.slack_view import SlackNewConversationView
from slack_sdk.errors import SlackApiError
from storage.slack_user import SlackUser

from openhands.integrations.service_types import ProviderTimeoutError
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
    """Create a SlackNewConversationView instance for testing."""
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


@pytest.mark.parametrize(
    'message,expected',
    [
        ('OpenHands/Openhands', 'OpenHands/Openhands'),
        ('deploy repo', 'deploy'),
        ('use hello world', None),
    ],
)
def test_infer_repo_from_message(message, expected, slack_manager):
    # Test the extracted function
    result = slack_manager._infer_repo_from_message(message)
    assert result == expected


@pytest.mark.parametrize(
    'description,expected',
    [
        # Basic pattern
        ('repo:OpenHands/OpenHands', 'OpenHands/OpenHands'),
        # With additional text before
        (
            'This channel is for repo:OpenHands/OpenHands discussions',
            'OpenHands/OpenHands',
        ),
        # With additional text after
        ('repo:owner/my-repo - please use this for issues', 'owner/my-repo'),
        # Case insensitive
        ('Repo:MyOrg/MyProject', 'MyOrg/MyProject'),
        ('REPO:org/proj', 'org/proj'),
        # With dots and underscores in name
        ('repo:my.org/my_repo.name', 'my.org/my_repo.name'),
        # No repo pattern
        ('This is just a regular description', None),
        # Empty string
        ('', None),
        # None
        (None, None),
        # Similar but not matching pattern
        ('repository:owner/repo', None),
    ],
)
def test_parse_repo_from_channel_description(description, expected, slack_manager):
    result = slack_manager._parse_repo_from_channel_description(description)
    assert result == expected


@pytest.mark.asyncio
async def test_get_default_repo_from_channel_with_purpose(slack_manager):
    """Test getting default repo from channel purpose field."""
    mock_client = MagicMock()
    mock_client.conversations_info = AsyncMock(
        return_value={
            'ok': True,
            'channel': {
                'purpose': {'value': 'This channel is for repo:OpenHands/OpenHands'},
                'topic': {'value': ''},
            },
        }
    )
    with patch(
        'integrations.slack.slack_manager.AsyncWebClient', return_value=mock_client
    ):
        result = await slack_manager._get_default_repo_from_channel(
            'C12345', 'xoxb-token'
        )
        assert result == 'OpenHands/OpenHands'


@pytest.mark.asyncio
async def test_get_default_repo_from_channel_with_topic(slack_manager):
    """Test getting default repo from channel topic when purpose has no repo."""
    mock_client = MagicMock()
    mock_client.conversations_info = AsyncMock(
        return_value={
            'ok': True,
            'channel': {
                'purpose': {'value': 'General discussion'},
                'topic': {'value': 'Current focus: repo:owner/my-repo'},
            },
        }
    )
    with patch(
        'integrations.slack.slack_manager.AsyncWebClient', return_value=mock_client
    ):
        result = await slack_manager._get_default_repo_from_channel(
            'C12345', 'xoxb-token'
        )
        assert result == 'owner/my-repo'


@pytest.mark.asyncio
async def test_get_default_repo_from_channel_no_repo(slack_manager):
    """Test when channel has no repo configured."""
    mock_client = MagicMock()
    mock_client.conversations_info = AsyncMock(
        return_value={
            'ok': True,
            'channel': {
                'purpose': {'value': 'Just a regular channel'},
                'topic': {'value': 'No repo here'},
            },
        }
    )
    with patch(
        'integrations.slack.slack_manager.AsyncWebClient', return_value=mock_client
    ):
        result = await slack_manager._get_default_repo_from_channel(
            'C12345', 'xoxb-token'
        )
        assert result is None


@pytest.mark.asyncio
async def test_get_default_repo_from_channel_slack_api_error(slack_manager):
    """Test handling of SlackApiError specifically."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = {'ok': False, 'error': 'channel_not_found'}
    mock_client.conversations_info = AsyncMock(
        side_effect=SlackApiError(message='API Error', response=mock_response)
    )
    with patch(
        'integrations.slack.slack_manager.AsyncWebClient', return_value=mock_client
    ):
        result = await slack_manager._get_default_repo_from_channel(
            'C12345', 'xoxb-token'
        )
        assert result is None


@pytest.mark.asyncio
async def test_get_default_repo_from_channel_generic_error(slack_manager):
    """Test handling of generic exceptions."""
    mock_client = MagicMock()
    mock_client.conversations_info = AsyncMock(
        side_effect=Exception('Unexpected error')
    )
    with patch(
        'integrations.slack.slack_manager.AsyncWebClient', return_value=mock_client
    ):
        result = await slack_manager._get_default_repo_from_channel(
            'C12345', 'xoxb-token'
        )
        assert result is None


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
        mock_get_repositories.side_effect = ProviderTimeoutError(
            'github API request timed out: ConnectTimeout'
        )

        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view
        )

        assert result is False
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args
        message = call_args[0][0]
        assert 'timed out' in message
        assert 'repository name' in message
        assert 'owner/repo-name' in message
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
        mock_get_repositories.return_value = []

        result = await slack_manager.is_job_requested(
            MagicMock(), slack_new_conversation_view
        )

        assert result is False
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args
        message = call_args[0][0]
        assert 'timed out' not in str(message)
        assert isinstance(message, dict)
        assert message.get('text') == 'Choose a Repository:'
