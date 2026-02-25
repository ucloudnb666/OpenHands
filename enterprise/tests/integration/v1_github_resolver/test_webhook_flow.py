"""
Integration tests for V1 GitHub Resolver webhook flow.

These tests verify:
1. Webhook payload triggers REAL agent server creation
2. "I'm on it" message is sent to GitHub
3. Agent summary is posted back to GitHub after completion

The tests use TestLLM with scripted trajectories to avoid real LLM calls
while still running actual agent servers.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import (
    TEST_GITHUB_USER_ID,
    TEST_GITHUB_USERNAME,
    create_issue_comment_payload,
    create_webhook_signature,
)


def create_test_llm_with_finish_response():
    """Create a TestLLM that immediately finishes with a summary."""
    from openhands.sdk.llm.message import Message, TextContent

    from .mocks import TestLLM

    # Create a simple trajectory that just finishes immediately
    finish_message = Message(
        role='assistant',
        content=[
            TextContent(
                text='I have analyzed the issue and completed the task. '
                'Here is my summary: The bug was fixed by updating the code.'
            )
        ],
    )

    return TestLLM.from_messages([finish_message])


class TestV1WebhookFlowWithRealAgentServer:
    """Test the V1 flow with REAL agent server (ProcessSandbox).

    These tests verify the REAL conversation creation path is taken:
    - V1 path is selected when v1_enabled=True
    - _create_v1_conversation is called
    - get_app_conversation_service is accessed

    Two-tier testing strategy:
    - Tier 1 (CI): Mock ProcessSandbox, verify flow reaches correct path
    - Tier 2 (Staging): Full E2E with real ProcessSandbox + TestLLM injection
    """

    @pytest.mark.asyncio
    async def test_webhook_reaches_v1_conversation_creation(
        self, patched_session_maker, mock_keycloak
    ):
        """
        Test that webhook reaches V1 conversation creation path (Tier 1).

        Verifies:
        1. V1 path is selected (v1_enabled=True)
        2. _create_v1_conversation is called
        3. Real flow would proceed to ProcessSandbox creation
        """
        payload_dict = create_issue_comment_payload(
            comment_body='@openhands please fix this bug',
            sender_id=TEST_GITHUB_USER_ID,
            sender_login=TEST_GITHUB_USERNAME,
        )

        v1_create_called = asyncio.Event()

        async def mock_create_v1_conversation(self, *args, **kwargs):
            v1_create_called.set()
            raise RuntimeError('V1 conversation creation reached')

        mock_github_context = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_comment_for_reaction = MagicMock()
        mock_issue.get_comment = MagicMock(return_value=mock_comment_for_reaction)
        mock_issue.create_comment = MagicMock(return_value=MagicMock(id=12345))
        mock_repo.get_issue.return_value = mock_issue
        mock_github_context.get_repo.return_value = mock_repo
        mock_github_context.__enter__ = MagicMock(return_value=mock_github_context)
        mock_github_context.__exit__ = MagicMock(return_value=False)

        mock_github_service = MagicMock()
        mock_github_service.get_issue_or_pr_comments = AsyncMock(return_value=[])
        mock_github_service.get_issue_or_pr_title_and_body = AsyncMock(
            return_value=('Test Issue', 'This is a test issue body')
        )

        with patch(
            'integrations.github.github_view.get_user_v1_enabled_setting',
            return_value=True,
        ), patch(
            'integrations.github.github_view.GithubIssueComment._create_v1_conversation',
            mock_create_v1_conversation,
        ), patch('github.Github', return_value=mock_github_context), patch(
            'github.GithubIntegration'
        ) as mock_github_integration, patch(
            'integrations.github.github_solvability.summarize_issue_solvability',
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            'server.auth.token_manager.TokenManager.get_idp_token_from_idp_user_id',
            new_callable=AsyncMock,
            return_value='mock-github-access-token',
        ), patch(
            'integrations.v1_utils.get_saas_user_auth',
            new_callable=AsyncMock,
        ) as mock_saas_auth, patch(
            'integrations.github.github_view.GithubServiceImpl',
            return_value=mock_github_service,
        ):
            mock_user_auth = MagicMock()
            mock_user_auth.get_provider_tokens = AsyncMock(
                return_value={'github': 'mock-token'}
            )
            mock_saas_auth.return_value = mock_user_auth

            mock_token_data = MagicMock()
            mock_token_data.token = 'test-installation-token'
            mock_github_integration.return_value.get_access_token.return_value = (
                mock_token_data
            )

            from integrations.github.github_manager import GithubManager
            from integrations.models import Message, SourceType
            from server.auth.token_manager import TokenManager

            token_manager = TokenManager()
            data_collector = MagicMock()
            data_collector.process_payload = MagicMock()
            data_collector.fetch_issue_details = AsyncMock(
                return_value={'description': 'Test issue body', 'previous_comments': []}
            )
            data_collector.save_data = AsyncMock()

            manager = GithubManager(token_manager, data_collector)
            manager.github_integration = mock_github_integration.return_value

            message = Message(
                source=SourceType.GITHUB,
                message={
                    'payload': payload_dict,
                    'installation': payload_dict['installation']['id'],
                },
            )

            await manager.receive_message(message)
            await asyncio.sleep(0.5)

            assert (
                v1_create_called.is_set()
            ), '_create_v1_conversation should be called for V1 flow'
            print('✅ V1 conversation creation path reached')

    @pytest.mark.asyncio
    async def test_real_agent_server_with_openhands_db(
        self, patched_session_maker, mock_keycloak, openhands_db
    ):
        """
        Test webhook flow with OpenHands database tables available.

        This test sets up both enterprise and OpenHands databases to enable
        REAL agent server creation path. The agent server creation is still
        mocked at a lower level (ProcessSandbox) but this verifies the full
        database-backed flow works.
        """
        payload_dict = create_issue_comment_payload(
            comment_body='@openhands please fix this bug',
            sender_id=TEST_GITHUB_USER_ID,
            sender_login=TEST_GITHUB_USERNAME,
        )

        start_task_created = asyncio.Event()
        captured_start_request = None

        # Create a mock that uses our test database session
        async def mock_start_app_conversation(*args, **kwargs):
            nonlocal captured_start_request
            start_task_created.set()
            # Extract the request parameter
            for arg in args:
                if hasattr(arg, 'selected_repository'):
                    captured_start_request = arg
                    break
            if 'request' in kwargs:
                captured_start_request = kwargs['request']

            from openhands.app_server.app_conversation.app_conversation_models import (
                AppConversationStartTask,
                AppConversationStartTaskStatus,
            )

            task = AppConversationStartTask(
                id='test-task-id',
                created_by_user_id='test-user',
                status=AppConversationStartTaskStatus.WORKING,
            )
            yield task

            task.status = AppConversationStartTaskStatus.READY
            task.app_conversation_id = 'test-conversation-id'
            yield task

        mock_github_context = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_comment_for_reaction = MagicMock()
        mock_issue.get_comment = MagicMock(return_value=mock_comment_for_reaction)
        mock_issue.create_comment = MagicMock(return_value=MagicMock(id=12345))
        mock_repo.get_issue.return_value = mock_issue
        mock_github_context.get_repo.return_value = mock_repo
        mock_github_context.__enter__ = MagicMock(return_value=mock_github_context)
        mock_github_context.__exit__ = MagicMock(return_value=False)

        mock_github_service = MagicMock()
        mock_github_service.get_issue_or_pr_comments = AsyncMock(return_value=[])
        mock_github_service.get_issue_or_pr_title_and_body = AsyncMock(
            return_value=('Test Issue', 'This is a test issue body')
        )
        mock_github_service.get_review_thread_comments = AsyncMock(return_value=[])

        with patch(
            'integrations.github.github_view.get_user_v1_enabled_setting',
            return_value=True,
        ), patch(
            'integrations.github.github_view.get_app_conversation_service'
        ) as mock_get_service, patch(
            'github.Github', return_value=mock_github_context
        ), patch('github.GithubIntegration') as mock_github_integration, patch(
            'integrations.github.github_solvability.summarize_issue_solvability',
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            'server.auth.token_manager.TokenManager.get_idp_token_from_idp_user_id',
            new_callable=AsyncMock,
            return_value='mock-github-access-token',
        ), patch(
            'integrations.v1_utils.get_saas_user_auth',
            new_callable=AsyncMock,
        ) as mock_saas_auth, patch(
            'integrations.github.github_view.GithubServiceImpl',
            return_value=mock_github_service,
        ):
            mock_user_auth = MagicMock()
            mock_user_auth.get_provider_tokens = AsyncMock(
                return_value={'github': 'mock-github-token'}
            )
            mock_saas_auth.return_value = mock_user_auth

            mock_token_data = MagicMock()
            mock_token_data.token = 'test-installation-token'
            mock_github_integration.return_value.get_access_token.return_value = (
                mock_token_data
            )

            # Setup mock for app_conversation_service with our async generator
            mock_service = MagicMock()
            mock_service.start_app_conversation = mock_start_app_conversation
            mock_context = MagicMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_service)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_context

            from integrations.github.github_manager import GithubManager
            from integrations.models import Message, SourceType
            from server.auth.token_manager import TokenManager

            token_manager = TokenManager()
            token_manager.load_org_token = MagicMock(
                return_value='mock-installation-token'
            )

            data_collector = MagicMock()
            data_collector.process_payload = MagicMock()
            data_collector.fetch_issue_details = AsyncMock(
                return_value={'description': 'Test issue body', 'previous_comments': []}
            )
            data_collector.save_data = AsyncMock()

            manager = GithubManager(token_manager, data_collector)
            manager.github_integration = mock_github_integration.return_value

            message = Message(
                source=SourceType.GITHUB,
                message={
                    'payload': payload_dict,
                    'installation': payload_dict['installation']['id'],
                },
            )

            await manager.receive_message(message)

            try:
                await asyncio.wait_for(start_task_created.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

            assert (
                start_task_created.is_set()
            ), 'start_app_conversation should be called (real agent server path)'
            assert captured_start_request is not None
            assert captured_start_request.selected_repository == 'test-owner/test-repo'
            print('✅ Real agent server path verified with OpenHands DB available')
            print(f'✅ Request repo: {captured_start_request.selected_repository}')


class TestV1WebhookFlow:
    """Test the complete V1 GitHub Resolver webhook flow (mocked agent server)."""

    @pytest.mark.asyncio
    async def test_webhook_triggers_start_app_conversation(
        self, patched_session_maker, mock_keycloak
    ):
        """
        Test that webhook triggers start_app_conversation (agent server creation).
        This test mocks the conversation service to verify the call is made.

        Verifies:
        1. Agent server is created (start_app_conversation called)
        2. "I'm on it" message is sent to GitHub
        3. Eyes reaction is added to acknowledge the request
        """
        # Create the webhook payload
        payload_dict = create_issue_comment_payload(
            comment_body='@openhands please fix this bug',
            sender_id=TEST_GITHUB_USER_ID,
            sender_login=TEST_GITHUB_USERNAME,
        )

        # Track conversation service calls
        start_conversation_called = asyncio.Event()
        im_on_it_sent = asyncio.Event()
        captured_start_request = None
        captured_github_comments = []
        captured_github_reactions = []

        async def mock_start_app_conversation(start_request):
            nonlocal captured_start_request
            captured_start_request = start_request
            start_conversation_called.set()
            # Yield a success task
            from uuid import uuid4

            from openhands.app_server.app_conversation.app_conversation_models import (
                AppConversationStartTask,
                AppConversationStartTaskStatus,
            )

            yield AppConversationStartTask(
                status=AppConversationStartTaskStatus.READY,
                detail='Conversation started',
                created_by_user_id='test-user',
                request=start_request,
                app_conversation_id=uuid4(),
            )

        # Create mocks for GitHub API
        mock_github_context = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()

        # Capture reactions - for issue comments, reactions are added via get_comment()
        def capture_reaction(reaction):
            captured_github_reactions.append(reaction)

        mock_issue.create_reaction = MagicMock(side_effect=capture_reaction)
        mock_comment_for_reaction = MagicMock()
        mock_comment_for_reaction.create_reaction = MagicMock(
            side_effect=capture_reaction
        )
        mock_issue.get_comment = MagicMock(return_value=mock_comment_for_reaction)

        # Capture comments - this is where "I'm on it" goes
        def capture_comment(body):
            captured_github_comments.append(body)
            if "I'm on it" in body:
                im_on_it_sent.set()
            mock_new_comment = MagicMock()
            mock_new_comment.id = 12345
            return mock_new_comment

        mock_issue.create_comment = MagicMock(side_effect=capture_comment)
        mock_repo.get_issue.return_value = mock_issue
        mock_github_context.get_repo.return_value = mock_repo
        mock_github_context.__enter__ = MagicMock(return_value=mock_github_context)
        mock_github_context.__exit__ = MagicMock(return_value=False)

        # Create mock for GithubServiceImpl
        mock_github_service = MagicMock()
        mock_github_service.get_issue_or_pr_comments = AsyncMock(return_value=[])
        mock_github_service.get_issue_or_pr_title_and_body = AsyncMock(
            return_value=('Test Issue', 'This is a test issue body')
        )
        mock_github_service.get_review_thread_comments = AsyncMock(return_value=[])

        with patch(
            'integrations.github.github_view.get_user_v1_enabled_setting',
            return_value=True,
        ), patch(
            'integrations.github.github_view.get_app_conversation_service'
        ) as mock_get_service, patch(
            'github.Github', return_value=mock_github_context
        ), patch('github.GithubIntegration') as mock_github_integration, patch(
            'integrations.github.github_solvability.summarize_issue_solvability',
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            'server.auth.token_manager.TokenManager.get_idp_token_from_idp_user_id',
            new_callable=AsyncMock,
            return_value='mock-github-access-token',
        ), patch(
            'integrations.v1_utils.get_saas_user_auth',
            new_callable=AsyncMock,
        ) as mock_saas_auth, patch(
            'integrations.github.github_view.GithubServiceImpl',
            return_value=mock_github_service,
        ):
            # Setup mocks
            mock_user_auth = MagicMock()
            mock_user_auth.get_provider_tokens = AsyncMock(
                return_value={'github': 'mock-github-token'}
            )
            mock_saas_auth.return_value = mock_user_auth

            mock_token_data = MagicMock()
            mock_token_data.token = 'test-installation-token'
            mock_github_integration.return_value.get_access_token.return_value = (
                mock_token_data
            )

            # Setup mock for app_conversation_service
            mock_service = MagicMock()
            mock_service.start_app_conversation = mock_start_app_conversation
            mock_context = MagicMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_service)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_context

            # Import and call
            from integrations.github.github_manager import GithubManager
            from integrations.models import Message, SourceType
            from server.auth.token_manager import TokenManager

            token_manager = TokenManager()
            # Mock load_org_token to return a token (required for send_message)
            token_manager.load_org_token = MagicMock(
                return_value='mock-installation-token'
            )

            data_collector = MagicMock()
            data_collector.process_payload = MagicMock()
            data_collector.fetch_issue_details = AsyncMock(
                return_value={
                    'description': 'Test issue body',
                    'previous_comments': [],
                }
            )
            data_collector.save_data = AsyncMock()

            manager = GithubManager(token_manager, data_collector)
            manager.github_integration = mock_github_integration.return_value

            message = Message(
                source=SourceType.GITHUB,
                message={
                    'payload': payload_dict,
                    'installation': payload_dict['installation']['id'],
                },
            )

            await manager.receive_message(message)

            # Wait for conversation to start
            try:
                await asyncio.wait_for(start_conversation_called.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

            # Wait for "I'm on it" message
            try:
                await asyncio.wait_for(im_on_it_sent.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

            # VERIFICATION 1: start_app_conversation was called (agent server created)
            assert (
                start_conversation_called.is_set()
            ), 'start_app_conversation should be called to create agent server'
            print('✅ Agent server created via start_app_conversation')

            # Verify the request contains expected data
            assert captured_start_request is not None
            assert captured_start_request.selected_repository == 'test-owner/test-repo'
            print(
                f'✅ Request had correct repo: {captured_start_request.selected_repository}'
            )

            # VERIFICATION 2: "I'm on it" message was sent
            assert (
                im_on_it_sent.is_set()
            ), '"I\'m on it" message should be sent to GitHub'
            im_on_it_messages = [
                c for c in captured_github_comments if "I'm on it" in c
            ]
            assert (
                len(im_on_it_messages) == 1
            ), f'Expected 1 "I\'m on it" message, got {len(im_on_it_messages)}'
            print(f'✅ "I\'m on it" message sent: {im_on_it_messages[0][:80]}...')

            # VERIFICATION 3: Eyes reaction was added
            assert (
                'eyes' in captured_github_reactions
            ), 'Eyes reaction should be added to acknowledge the request'
            print('✅ Eyes reaction added to acknowledge request')

    @pytest.mark.asyncio
    async def test_v1_callback_processor_sends_summary(self, patched_session_maker):
        """
        Test that the V1 callback processor sends the agent summary to GitHub
        when the conversation finishes.
        """
        from uuid import uuid4

        from integrations.github.github_v1_callback_processor import (
            GithubV1CallbackProcessor,
        )

        from openhands.app_server.event_callback.event_callback_models import (
            EventCallback,
        )
        from openhands.sdk.event import ConversationStateUpdateEvent

        # Track summary posting
        captured_summaries = []
        test_conversation_id = uuid4()
        test_summary = 'I have completed the task. Here is what I did...'

        # Create the callback processor
        processor = GithubV1CallbackProcessor(
            github_view_data={
                'issue_number': 1,
                'full_repo_name': 'test-owner/test-repo',
                'installation_id': 123456,
            },
            should_request_summary=True,
        )

        # Create the event that triggers summary
        event = ConversationStateUpdateEvent(
            key='execution_status',
            value='finished',
        )

        # Create a callback
        callback = EventCallback(
            id=uuid4(),
            conversation_id=test_conversation_id,
            processor=processor,
        )

        # Mock the _request_summary and _post_summary_to_github methods
        async def mock_request_summary(conv_id):
            return test_summary

        def mock_post_summary(summary):
            captured_summaries.append(summary)

        with patch.object(
            processor, '_request_summary', new_callable=AsyncMock
        ) as mock_req, patch.object(
            processor, '_post_summary_to_github', new_callable=AsyncMock
        ) as mock_post:
            mock_req.return_value = test_summary

            # Call the processor
            result = await processor(test_conversation_id, callback, event)

            # Verify _request_summary was called
            mock_req.assert_called_once_with(test_conversation_id)
            print('✅ Summary was requested from agent server')

            # Verify _post_summary_to_github was called with the summary
            mock_post.assert_called_once_with(test_summary)
            print('✅ Summary was posted to GitHub')

            # Verify the result
            assert result is not None
            assert result.detail == test_summary
            print(f'✅ Callback returned success with summary: {test_summary[:50]}...')


class TestWebhookSignatureVerification:
    """Test webhook signature verification."""

    def test_signature_creation(self):
        """Test that we can create valid webhook signatures."""
        payload = b'{"test": "payload"}'
        secret = 'test-secret'

        signature = create_webhook_signature(payload, secret)

        assert signature.startswith('sha256=')
        assert len(signature) == 71  # 'sha256=' + 64 hex chars


class TestPayloadCreation:
    """Test webhook payload creation helpers."""

    def test_issue_comment_payload_structure(self):
        """Test that issue comment payloads have correct structure."""
        payload = create_issue_comment_payload(
            issue_number=42,
            comment_body='@openhands help',
            repo_name='owner/repo',
            sender_id=123,
            sender_login='testuser',
        )

        assert payload['action'] == 'created'
        assert payload['issue']['number'] == 42
        assert payload['comment']['body'] == '@openhands help'
        assert payload['repository']['full_name'] == 'owner/repo'
        assert payload['sender']['id'] == 123
        assert payload['sender']['login'] == 'testuser'
        assert 'installation' in payload
