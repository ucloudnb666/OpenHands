"""
Unit tests for AutomationEventService.

Tests the service that forwards GitHub webhook events to the automation service.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch the constants before importing the module
PATCHES = [
    patch('server.services.automation_event_service.GITHUB_APP_CLIENT_ID', 'test-client-id'),
    patch('server.services.automation_event_service.GITHUB_APP_PRIVATE_KEY', 'test-private-key'),
    patch('server.services.automation_event_service.GITHUB_APP_WEBHOOK_SECRET', 'test-secret'),
]


@pytest.fixture
def mock_token_manager():
    """Create a mock TokenManager."""
    return MagicMock()


@pytest.fixture
def mock_org_git_claim():
    """Create a mock OrgGitClaim."""
    claim = MagicMock()
    claim.org_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
    return claim


@pytest.fixture
def github_org_payload():
    """Create a sample GitHub webhook payload for an organization repo."""
    return {
        'repository': {
            'id': 123456,
            'full_name': 'test-org/test-repo',
            'private': False,
            'default_branch': 'main',
            'owner': {
                'login': 'test-org',
                'id': 789,
                'type': 'Organization',
            },
        },
        'sender': {
            'id': 12345,
            'login': 'testuser',
        },
        'action': 'opened',
        'installation': {
            'id': 99999,
        },
    }


@pytest.fixture
def github_user_payload():
    """Create a sample GitHub webhook payload for a personal/user repo."""
    return {
        'repository': {
            'id': 654321,
            'full_name': 'testuser/personal-repo',
            'private': True,
            'default_branch': 'main',
            'owner': {
                'login': 'testuser',
                'id': 12345,
                'type': 'User',
            },
        },
        'sender': {
            'id': 12345,
            'login': 'testuser',
        },
        'action': 'opened',
        'installation': {
            'id': 99999,
        },
    }


def create_service(mock_token_manager):
    """Helper to create a service with all necessary mocks."""
    with patch('server.services.automation_event_service.GithubIntegration'), \
         patch('server.services.automation_event_service.Auth.AppAuth'):
        from server.services.automation_event_service import AutomationEventService
        return AutomationEventService(mock_token_manager)


class TestResolveGithubOrg:
    """Tests for _resolve_github_org method."""

    @pytest.mark.asyncio
    async def test_resolve_github_org_found(self, mock_token_manager, mock_org_git_claim):
        """
        GIVEN: A GitHub org that has been claimed in OpenHands
        WHEN: _resolve_github_org is called
        THEN: The OpenHands org_id is returned
        """
        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=mock_org_git_claim,
        ) as mock_get_claim:
            service = create_service(mock_token_manager)
            result = await service._resolve_github_org('test-org')

            assert result == mock_org_git_claim.org_id
            mock_get_claim.assert_called_once_with(
                provider='github',
                git_organization='test-org',
            )

    @pytest.mark.asyncio
    async def test_resolve_github_org_not_found(self, mock_token_manager):
        """
        GIVEN: A GitHub org that has NOT been claimed in OpenHands
        WHEN: _resolve_github_org is called
        THEN: None is returned
        """
        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=None,
        ):
            service = create_service(mock_token_manager)
            result = await service._resolve_github_org('unclaimed-org')

            assert result is None

    @pytest.mark.asyncio
    async def test_resolve_github_org_lowercases_name(self, mock_token_manager):
        """
        GIVEN: A GitHub org name with mixed case
        WHEN: _resolve_github_org is called
        THEN: The org name is lowercased for lookup
        """
        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_get_claim:
            service = create_service(mock_token_manager)
            await service._resolve_github_org('Test-Org')

            mock_get_claim.assert_called_once_with(
                provider='github',
                git_organization='test-org',
            )


class TestResolvePersonalOrg:
    """Tests for _resolve_personal_org method."""

    @pytest.mark.asyncio
    async def test_resolve_personal_org_success(self, mock_token_manager):
        """
        GIVEN: A GitHub user ID that maps to a keycloak user
        WHEN: _resolve_personal_org is called
        THEN: The keycloak user ID is returned as a UUID (personal org)
        """
        keycloak_id = '87654321-4321-8765-4321-876543218765'
        mock_token_manager.get_user_id_from_idp_user_id = AsyncMock(
            return_value=keycloak_id
        )

        service = create_service(mock_token_manager)
        result = await service._resolve_personal_org(12345)

        assert result == uuid.UUID(keycloak_id)
        mock_token_manager.get_user_id_from_idp_user_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_personal_org_no_github_user_id(self, mock_token_manager):
        """
        GIVEN: No GitHub user ID provided
        WHEN: _resolve_personal_org is called
        THEN: None is returned
        """
        service = create_service(mock_token_manager)
        result = await service._resolve_personal_org(None)

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_personal_org_user_not_found(self, mock_token_manager):
        """
        GIVEN: A GitHub user ID that doesn't map to a keycloak user
        WHEN: _resolve_personal_org is called
        THEN: None is returned
        """
        mock_token_manager.get_user_id_from_idp_user_id = AsyncMock(return_value=None)

        service = create_service(mock_token_manager)
        result = await service._resolve_personal_org(12345)

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_personal_org_exception(self, mock_token_manager):
        """
        GIVEN: An exception occurs during keycloak lookup
        WHEN: _resolve_personal_org is called
        THEN: None is returned and warning is logged
        """
        mock_token_manager.get_user_id_from_idp_user_id = AsyncMock(
            side_effect=Exception('Keycloak error')
        )

        service = create_service(mock_token_manager)
        result = await service._resolve_personal_org(12345)

        assert result is None


class TestForwardGithubEvent:
    """Tests for forward_github_event method."""

    @pytest.mark.asyncio
    async def test_forward_org_event_success(
        self, mock_token_manager, github_org_payload, mock_org_git_claim
    ):
        """
        GIVEN: A GitHub event from a claimed organization repo
        WHEN: forward_github_event is called
        THEN: Event is forwarded to automation service
        """
        from server.services.automation_event_service import AutomationEventService

        keycloak_id = '87654321-4321-8765-4321-876543218765'
        mock_token_manager.get_user_id_from_idp_user_id = AsyncMock(
            return_value=keycloak_id
        )

        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=mock_org_git_claim,
        ), patch(
            'server.services.automation_event_service.OrgMemberStore.get_org_member',
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ), patch(
            'server.services.automation_event_service.GithubIntegration'
        ), patch(
            'server.services.automation_event_service.Auth.AppAuth'
        ), patch.object(
            AutomationEventService,
            '_send_to_automation_service',
            new_callable=AsyncMock,
        ) as mock_send, patch.object(
            AutomationEventService,
            '_check_github_org_membership',
            new_callable=AsyncMock,
            return_value=True,
        ):
            service = AutomationEventService(mock_token_manager)
            await service.forward_github_event(
                payload=github_org_payload,
                event_type='push',
                installation_id=99999,
            )

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][0] == mock_org_git_claim.org_id
            payload = call_args[0][1]
            assert payload['event_type'] == 'push'
            assert payload['organization']['github_org'] == 'test-org'

    @pytest.mark.asyncio
    async def test_forward_personal_repo_event_success(
        self, mock_token_manager, github_user_payload
    ):
        """
        GIVEN: A GitHub event from a personal repo with linked OpenHands account
        WHEN: forward_github_event is called
        THEN: Event is forwarded using the user's personal org (keycloak ID)
        """
        from server.services.automation_event_service import AutomationEventService

        keycloak_id = '87654321-4321-8765-4321-876543218765'
        mock_token_manager.get_user_id_from_idp_user_id = AsyncMock(
            return_value=keycloak_id
        )

        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=None,  # No org claim for personal repo
        ), patch(
            'server.services.automation_event_service.OrgMemberStore.get_org_member',
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ), patch(
            'server.services.automation_event_service.GithubIntegration'
        ), patch(
            'server.services.automation_event_service.Auth.AppAuth'
        ), patch.object(
            AutomationEventService,
            '_send_to_automation_service',
            new_callable=AsyncMock,
        ) as mock_send, patch.object(
            AutomationEventService,
            '_check_github_org_membership',
            new_callable=AsyncMock,
            return_value=True,
        ):
            service = AutomationEventService(mock_token_manager)
            await service.forward_github_event(
                payload=github_user_payload,
                event_type='push',
                installation_id=99999,
            )

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            # Personal org should be keycloak ID
            assert call_args[0][0] == uuid.UUID(keycloak_id)
            payload = call_args[0][1]
            assert payload['organization']['github_org'] == 'testuser'
            assert payload['organization']['openhands_org_id'] == keycloak_id

    @pytest.mark.asyncio
    async def test_forward_event_no_owner_in_payload(self, mock_token_manager):
        """
        GIVEN: A GitHub event with no repository owner in payload
        WHEN: forward_github_event is called
        THEN: Event is skipped with warning log
        """
        from server.services.automation_event_service import AutomationEventService

        payload = {
            'repository': {},
            'sender': {'id': 12345, 'login': 'testuser'},
        }

        with patch(
            'server.services.automation_event_service.GithubIntegration'
        ), patch(
            'server.services.automation_event_service.Auth.AppAuth'
        ), patch(
            'server.services.automation_event_service.logger'
        ) as mock_logger, patch.object(
            AutomationEventService,
            '_send_to_automation_service',
            new_callable=AsyncMock,
        ) as mock_send:
            service = AutomationEventService(mock_token_manager)
            await service.forward_github_event(
                payload=payload,
                event_type='push',
                installation_id=99999,
            )

            mock_send.assert_not_called()
            mock_logger.warning.assert_called()
            assert 'No repository owner' in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_forward_event_org_not_claimed_and_not_personal(
        self, mock_token_manager, github_org_payload
    ):
        """
        GIVEN: A GitHub event from an org that isn't claimed (and isn't personal)
        WHEN: forward_github_event is called
        THEN: Event is skipped with warning log
        """
        from server.services.automation_event_service import AutomationEventService

        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            'server.services.automation_event_service.GithubIntegration'
        ), patch(
            'server.services.automation_event_service.Auth.AppAuth'
        ), patch(
            'server.services.automation_event_service.logger'
        ) as mock_logger, patch.object(
            AutomationEventService,
            '_send_to_automation_service',
            new_callable=AsyncMock,
        ) as mock_send:
            service = AutomationEventService(mock_token_manager)
            await service.forward_github_event(
                payload=github_org_payload,
                event_type='push',
                installation_id=99999,
            )

            mock_send.assert_not_called()
            mock_logger.warning.assert_called()
            assert 'not claimed' in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_forward_personal_repo_no_openhands_account(
        self, mock_token_manager, github_user_payload
    ):
        """
        GIVEN: A GitHub event from a personal repo, but user has no OpenHands account
        WHEN: forward_github_event is called
        THEN: Event is skipped with warning log
        """
        from server.services.automation_event_service import AutomationEventService

        mock_token_manager.get_user_id_from_idp_user_id = AsyncMock(return_value=None)

        with patch(
            'server.services.automation_event_service.OrgGitClaimStore.get_claim_by_provider_and_git_org',
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            'server.services.automation_event_service.GithubIntegration'
        ), patch(
            'server.services.automation_event_service.Auth.AppAuth'
        ), patch(
            'server.services.automation_event_service.logger'
        ) as mock_logger, patch.object(
            AutomationEventService,
            '_send_to_automation_service',
            new_callable=AsyncMock,
        ) as mock_send:
            service = AutomationEventService(mock_token_manager)
            await service.forward_github_event(
                payload=github_user_payload,
                event_type='push',
                installation_id=99999,
            )

            mock_send.assert_not_called()
            mock_logger.warning.assert_called()
            assert 'no personal org found' in str(mock_logger.warning.call_args)


class TestInferEventType:
    """Tests for _infer_event_type method."""

    @pytest.mark.asyncio
    async def test_infer_pull_request(self, mock_token_manager):
        """Test inferring pull_request event type."""
        service = create_service(mock_token_manager)
        payload = {'pull_request': {'number': 1}}
        assert service._infer_event_type(payload) == 'pull_request'

    @pytest.mark.asyncio
    async def test_infer_issues(self, mock_token_manager):
        """Test inferring issues event type."""
        service = create_service(mock_token_manager)
        payload = {'issue': {'number': 1}}
        assert service._infer_event_type(payload) == 'issues'

    @pytest.mark.asyncio
    async def test_infer_issue_comment(self, mock_token_manager):
        """Test inferring issue_comment event type."""
        service = create_service(mock_token_manager)
        payload = {'issue': {'number': 1}, 'comment': {'body': 'test'}}
        assert service._infer_event_type(payload) == 'issue_comment'

    @pytest.mark.asyncio
    async def test_infer_push(self, mock_token_manager):
        """Test inferring push event type."""
        service = create_service(mock_token_manager)
        payload = {'ref': 'refs/heads/main', 'commits': []}
        assert service._infer_event_type(payload) == 'push'

    @pytest.mark.asyncio
    async def test_infer_unknown(self, mock_token_manager):
        """Test inferring unknown event type."""
        service = create_service(mock_token_manager)
        payload = {'some_unknown_key': 'value'}
        assert service._infer_event_type(payload) == 'unknown'


class TestCheckGithubOrgMembership:
    """Tests for _check_github_org_membership method."""

    @pytest.mark.asyncio
    async def test_private_repo_returns_true(self, mock_token_manager):
        """
        GIVEN: A private repository
        WHEN: _check_github_org_membership is called
        THEN: True is returned (access implies membership)
        """
        payload = {
            'repository': {'private': True, 'owner': {'type': 'Organization'}},
        }

        service = create_service(mock_token_manager)
        result = await service._check_github_org_membership(
            payload, 99999, 'testuser'
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_personal_repo_owner_is_member(self, mock_token_manager):
        """
        GIVEN: A personal repo (not org) where user is the owner
        WHEN: _check_github_org_membership is called
        THEN: True is returned
        """
        payload = {
            'repository': {
                'private': False,
                'owner': {'type': 'User', 'login': 'testuser'},
            },
        }

        service = create_service(mock_token_manager)
        result = await service._check_github_org_membership(
            payload, 99999, 'testuser'
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_personal_repo_non_owner_not_member(self, mock_token_manager):
        """
        GIVEN: A personal repo (not org) where user is NOT the owner
        WHEN: _check_github_org_membership is called
        THEN: False is returned
        """
        payload = {
            'repository': {
                'private': False,
                'owner': {'type': 'User', 'login': 'otheruser'},
            },
        }

        service = create_service(mock_token_manager)
        result = await service._check_github_org_membership(
            payload, 99999, 'testuser'
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_username_returns_false(self, mock_token_manager):
        """
        GIVEN: No username provided
        WHEN: _check_github_org_membership is called
        THEN: False is returned
        """
        payload = {
            'repository': {'private': False, 'owner': {'type': 'Organization'}},
        }

        service = create_service(mock_token_manager)
        result = await service._check_github_org_membership(payload, 99999, None)
        assert result is False


class TestCheckOpenhandsOrgMembership:
    """Tests for _check_openhands_org_membership method."""

    @pytest.mark.asyncio
    async def test_member_found(self, mock_token_manager):
        """
        GIVEN: User is a member of the OpenHands org
        WHEN: _check_openhands_org_membership is called
        THEN: True is returned
        """
        org_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
        keycloak_id = '87654321-4321-8765-4321-876543218765'

        with patch(
            'server.services.automation_event_service.OrgMemberStore.get_org_member',
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ):
            service = create_service(mock_token_manager)
            result = await service._check_openhands_org_membership(org_id, keycloak_id)
            assert result is True

    @pytest.mark.asyncio
    async def test_member_not_found(self, mock_token_manager):
        """
        GIVEN: User is NOT a member of the OpenHands org
        WHEN: _check_openhands_org_membership is called
        THEN: False is returned
        """
        org_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
        keycloak_id = '87654321-4321-8765-4321-876543218765'

        with patch(
            'server.services.automation_event_service.OrgMemberStore.get_org_member',
            new_callable=AsyncMock,
            return_value=None,
        ):
            service = create_service(mock_token_manager)
            result = await service._check_openhands_org_membership(org_id, keycloak_id)
            assert result is False


class TestSendToAutomationService:
    """Tests for _send_to_automation_service method."""

    @pytest.mark.asyncio
    async def test_send_success(self, mock_token_manager):
        """
        GIVEN: AUTOMATION_SERVICE_URL is configured
        WHEN: _send_to_automation_service is called
        THEN: Request is sent with correct signature
        """
        org_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
        payload = {'event_type': 'push', 'test': 'data'}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'matched': 1})

        # Create proper async context manager mocks
        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__.return_value = mock_response

        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_post_cm

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session_instance

        with patch(
            'server.services.automation_event_service.AUTOMATION_SERVICE_URL',
            'https://automation.example.com',
        ), patch(
            'server.services.automation_event_service.GITHUB_APP_WEBHOOK_SECRET',
            'test-secret',
        ), patch(
            'server.services.automation_event_service.aiohttp.ClientSession',
            return_value=mock_session_cm,
        ):
            service = create_service(mock_token_manager)
            await service._send_to_automation_service(org_id, payload)

            mock_session_instance.post.assert_called_once()
            call_args = mock_session_instance.post.call_args
            assert str(org_id) in call_args[0][0]
            assert 'X-Hub-Signature-256' in call_args[1]['headers']

    @pytest.mark.asyncio
    async def test_send_no_url_configured(self, mock_token_manager):
        """
        GIVEN: AUTOMATION_SERVICE_URL is not configured
        WHEN: _send_to_automation_service is called
        THEN: Warning is logged and request is not sent
        """
        org_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
        payload = {'event_type': 'push'}

        with patch(
            'server.services.automation_event_service.AUTOMATION_SERVICE_URL',
            '',
        ), patch(
            'server.services.automation_event_service.logger'
        ) as mock_logger, patch(
            'aiohttp.ClientSession'
        ) as mock_session:
            service = create_service(mock_token_manager)
            await service._send_to_automation_service(org_id, payload)

            mock_session.assert_not_called()
            mock_logger.warning.assert_called()
            assert 'not configured' in str(mock_logger.warning.call_args)


class TestSignPayload:
    """Tests for _sign_payload method."""

    def test_sign_payload(self, mock_token_manager):
        """
        GIVEN: A payload to sign
        WHEN: _sign_payload is called
        THEN: A valid sha256 signature is returned
        """
        with patch(
            'server.services.automation_event_service.GITHUB_APP_WEBHOOK_SECRET',
            'test-secret',
        ):
            service = create_service(mock_token_manager)
            payload_bytes = b'{"test": "data"}'
            signature = service._sign_payload(payload_bytes)

            assert signature.startswith('sha256=')
            assert len(signature) == 71  # 'sha256=' + 64 hex chars
