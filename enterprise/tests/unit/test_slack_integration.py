from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integrations.slack.slack_manager import SlackManager


@pytest.fixture
def slack_manager():
    # Mock the token_manager constructor
    slack_manager = SlackManager(token_manager=MagicMock())
    return slack_manager


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
async def test_get_default_repo_from_channel_api_error(slack_manager):
    """Test handling of API errors."""
    mock_client = MagicMock()
    mock_client.conversations_info = AsyncMock(side_effect=Exception('API Error'))
    with patch(
        'integrations.slack.slack_manager.AsyncWebClient', return_value=mock_client
    ):
        result = await slack_manager._get_default_repo_from_channel(
            'C12345', 'xoxb-token'
        )
        assert result is None
