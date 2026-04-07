"""
Service for forwarding GitHub webhook events to the automation service.

This service handles:
1. Resolving GitHub org → OpenHands org_id (via OrgGitClaim)
2. For personal repos (owner type 'User'), resolving to personal OpenHands org
   (keycloak user ID)
3. Converting GitHub user ID → Keycloak user ID
4. Access control checks:
   - GitHub org membership (for both public and private repos)
   - OpenHands org membership (Keycloak user must be member of OpenHands org)
5. Forwarding payloads to the automation service
"""

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import aiohttp
from github import Auth, Github, GithubIntegration
from server.auth.constants import (
    AUTOMATION_SERVICE_URL,
    GITHUB_APP_CLIENT_ID,
    GITHUB_APP_PRIVATE_KEY,
    GITHUB_APP_WEBHOOK_SECRET,
)
from server.auth.token_manager import TokenManager
from storage.org_git_claim_store import OrgGitClaimStore
from storage.org_member_store import OrgMemberStore

from openhands.core.logger import openhands_logger as logger
from openhands.integrations.provider import ProviderType


@dataclass
class OrgContext:
    """Context for the resolved organization."""

    org_id: UUID
    github_org: str


@dataclass
class AccessControl:
    """Access control metadata for the event sender."""

    is_github_org_member: bool
    is_openhands_org_member: bool
    has_openhands_account: bool


class AutomationEventService:
    """Service for forwarding webhook events to the automation service."""

    def __init__(self, token_manager: TokenManager):
        from server.auth.constants import AUTOMATION_EVENT_FORWARDING_ENABLED

        self.token_manager = token_manager
        self.github_integration = GithubIntegration(
            auth=Auth.AppAuth(GITHUB_APP_CLIENT_ID, GITHUB_APP_PRIVATE_KEY)
        )

        # Fail fast if forwarding is enabled but misconfigured
        if AUTOMATION_EVENT_FORWARDING_ENABLED:
            if not AUTOMATION_SERVICE_URL:
                raise ValueError(
                    'AUTOMATION_EVENT_FORWARDING_ENABLED=true but '
                    'AUTOMATION_SERVICE_URL is not configured'
                )

    async def forward_github_event(
        self,
        payload: dict[str, Any],
        event_type: str | None,
        installation_id: int,
    ) -> None:
        """
        Forward a GitHub webhook event to the automation service.

        This is designed to be called as a fire-and-forget background task.

        Args:
            payload: The raw GitHub webhook payload
            event_type: The X-GitHub-Event header value (used for logging only)
            installation_id: The GitHub App installation ID
        """
        org_id: UUID | None = None
        try:
            # Resolve org context (org_id and github_org name)
            org_context = await self._resolve_org_context(payload)
            if not org_context:
                return

            org_id = org_context.org_id

            # Build access control metadata
            access_control = await self._build_access_control(
                payload, installation_id, org_context
            )

            # Build and send the event payload
            event_payload = self._build_event_payload(
                org_context, access_control, payload
            )
            await self._send_to_automation_service(org_id, event_payload)

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Network errors are expected and recoverable
            logger.error(
                f'[AutomationEventService] Network error forwarding event '
                f'(org_id={org_id}, event_type={event_type}): {e}',
                exc_info=True,
                extra={'installation_id': installation_id},
            )
            # TODO: Add metrics tracking for failed forwards
            # TODO: Consider retry mechanism for transient failures
        except Exception as e:
            # Log unexpected errors but re-raise to surface bugs
            logger.error(
                f'[AutomationEventService] Unexpected error forwarding event '
                f'(org_id={org_id}, event_type={event_type}): {e}',
                exc_info=True,
                extra={'installation_id': installation_id},
            )
            raise

    async def _resolve_org_context(self, payload: dict[str, Any]) -> OrgContext | None:
        """
        Resolve the organization context from the webhook payload.

        Returns None if the org cannot be resolved (not claimed, no personal org).
        """
        repo = payload.get('repository', {})
        owner = repo.get('owner', {})
        git_org_name = owner.get('login')
        owner_type = owner.get('type')  # 'User' or 'Organization'

        if not git_org_name:
            logger.warning(
                '[AutomationEventService] No repository owner in payload, skipping'
            )
            return None

        # Try to resolve via OrgGitClaim
        org_id = await self._resolve_github_org(git_org_name)

        # Fallback for personal repos
        if not org_id and owner_type == 'User':
            org_id = await self._resolve_personal_org(owner.get('id'))
            if org_id:
                logger.info(
                    f'[AutomationEventService] Resolved personal repo owner '
                    f'{git_org_name} to personal org {org_id}'
                )

        if not org_id:
            logger.warning(
                f'[AutomationEventService] GitHub org {git_org_name} not claimed '
                f'and no personal org found, skipping'
            )
            return None

        return OrgContext(org_id=org_id, github_org=git_org_name)

    async def _build_access_control(
        self,
        payload: dict[str, Any],
        installation_id: int,
        org_context: OrgContext,
    ) -> AccessControl:
        """Build access control metadata for the event sender."""
        sender = payload.get('sender', {})
        github_user_id = sender.get('id')
        github_username = sender.get('login')

        # Resolve Keycloak user ID
        keycloak_user_id = None
        if github_user_id:
            keycloak_user_id = await self._get_keycloak_user_id(github_user_id)

        # Check GitHub org membership
        # TODO: Consider caching membership results (TTL: 5-10 min) to reduce API calls
        is_github_org_member = await self._check_github_org_membership(
            payload, installation_id, github_username
        )

        # Check OpenHands org membership
        is_openhands_org_member = False
        if keycloak_user_id:
            is_openhands_org_member = await self._check_openhands_org_membership(
                org_context.org_id, keycloak_user_id
            )

        return AccessControl(
            is_github_org_member=is_github_org_member,
            is_openhands_org_member=is_openhands_org_member,
            has_openhands_account=keycloak_user_id is not None,
        )

    def _build_event_payload(
        self,
        org_context: OrgContext,
        access_control: AccessControl,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the event payload to forward to the automation service."""
        return {
            'organization': {
                'github_org': org_context.github_org,
                'openhands_org_id': str(org_context.org_id),
            },
            'access_control': {
                'is_github_org_member': access_control.is_github_org_member,
                'is_openhands_org_member': access_control.is_openhands_org_member,
                'has_openhands_account': access_control.has_openhands_account,
            },
            'raw_payload': raw_payload,
        }

    async def _resolve_github_org(self, git_org_name: str) -> UUID | None:
        """
        Resolve a GitHub organization name to an OpenHands org_id.

        Uses the existing OrgGitClaim system.
        """
        claim = await OrgGitClaimStore.get_claim_by_provider_and_git_org(
            provider='github',
            git_organization=git_org_name.lower(),
        )

        if claim:
            return claim.org_id
        return None

    async def _resolve_personal_org(self, github_user_id: int | None) -> UUID | None:
        """
        Resolve a GitHub user to their personal OpenHands org.

        For personal repos (owner type is 'User'), the OpenHands org_id
        is the user's keycloak user ID. This allows users to set up
        automations on their personal repos without needing an OrgGitClaim.
        """
        if not github_user_id:
            return None

        try:
            keycloak_id = await self._get_keycloak_user_id(github_user_id)
            if keycloak_id:
                return UUID(keycloak_id)
        except Exception as e:
            logger.warning(
                f'[AutomationEventService] Failed to resolve personal org for '
                f'GitHub user {github_user_id}: {e}'
            )
        return None

    async def _get_keycloak_user_id(self, github_user_id: int) -> str | None:
        """
        Convert a GitHub user ID to a Keycloak user ID.

        Uses TokenManager.get_user_id_from_idp_user_id().
        """
        try:
            keycloak_id = await self.token_manager.get_user_id_from_idp_user_id(
                str(github_user_id), ProviderType.GITHUB
            )
            return keycloak_id
        except Exception as e:
            logger.debug(
                f'[AutomationEventService] Failed to get keycloak ID for GitHub user {github_user_id}: {e}'
            )
            return None

    async def _check_github_org_membership(
        self,
        payload: dict[str, Any],
        installation_id: int,
        username: str | None,
    ) -> bool:
        """
        Check if the event sender is a member of the GitHub org.

        This check is performed for both public and private repos to ensure
        proper access control. For org repos, we verify org membership.
        For personal repos, the owner is the only "member".
        """
        if not username:
            return False

        repo = payload.get('repository', {})
        owner = repo.get('owner', {})

        # For personal repos (not org), owner is the only "member"
        if owner.get('type') != 'Organization':
            return username == owner.get('login')

        # For org repos (both public and private), check org membership via GitHub API
        try:
            org_name = owner.get('login')
            token = self._get_installation_token(installation_id)

            # Run blocking GitHub API calls in a thread pool to avoid blocking
            # the event loop
            return await asyncio.to_thread(
                self._check_org_membership_sync, org_name, username, token
            )
        except Exception as e:
            logger.debug(
                f'[AutomationEventService] Failed to check GitHub org membership for {username}: {e}'
            )
            # Fail closed - assume not a member if we can't verify
            return False

    async def _check_openhands_org_membership(
        self,
        org_id: UUID,
        keycloak_user_id: str,
    ) -> bool:
        """
        Check if the user is a member of the OpenHands organization.

        This ensures that only users who are part of the OpenHands org
        can trigger automations, even if they have GitHub org access.
        """
        try:
            member = await OrgMemberStore.get_org_member(
                org_id=org_id,
                user_id=UUID(keycloak_user_id),
            )
            return member is not None
        except Exception as e:
            logger.debug(
                f'[AutomationEventService] Failed to check OpenHands org membership '
                f'for user {keycloak_user_id} in org {org_id}: {e}'
            )
            # Fail closed - assume not a member if we can't verify
            return False

    def _get_installation_token(self, installation_id: int) -> str:
        """Get a GitHub installation access token."""
        token_data = self.github_integration.get_access_token(installation_id)
        return token_data.token

    def _check_org_membership_sync(
        self, org_name: str, username: str, token: str
    ) -> bool:
        """
        Synchronously check if a user is a member of a GitHub organization.

        This method is designed to be called via asyncio.to_thread() to avoid
        blocking the event loop with synchronous PyGithub API calls.
        """
        with Github(auth=Auth.Token(token)) as github_client:
            org = github_client.get_organization(org_name)
            user = github_client.get_user(username)
            # For org membership, we need NamedUser. The API guarantees
            # get_user(username) returns NamedUser for other users.
            if not hasattr(user, 'login'):
                raise TypeError(f'Expected NamedUser, got {type(user)}')
            return org.has_in_members(user)  # type: ignore[arg-type]

    def _sign_payload(self, payload_bytes: bytes) -> str:
        """
        Sign a payload using the GitHub webhook secret.

        Returns the signature in the format 'sha256=<hex_digest>'.
        """
        signature = hmac.new(
            GITHUB_APP_WEBHOOK_SECRET.encode('utf-8'),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f'sha256={signature}'

    async def _send_to_automation_service(
        self,
        org_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        """
        Send the normalized payload to the automation service.

        The payload is signed using the GitHub webhook secret so the
        automation service can verify it came from the OpenHands server.
        """
        if not AUTOMATION_SERVICE_URL:
            logger.warning(
                '[AutomationEventService] AUTOMATION_SERVICE_URL not configured'
            )
            return

        # Endpoint: /v1/events/{org_id}/github
        url = f'{AUTOMATION_SERVICE_URL.rstrip("/")}/v1/events/{org_id}/github'

        # Serialize payload to JSON bytes for signing
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        signature = self._sign_payload(payload_bytes)

        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Signature-256': signature,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=payload_bytes,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        logger.warning(
                            f'[AutomationEventService] Automation service returned '
                            f'{resp.status}: {body}'
                        )
                    else:
                        data = await resp.json()
                        matched = data.get('matched', 0)
                        logger.info(
                            f'[AutomationEventService] Forwarded event to org {org_id}: '
                            f'{matched} automations matched'
                        )
        except asyncio.TimeoutError:
            logger.warning(
                '[AutomationEventService] Timeout forwarding to automation service'
            )
        except aiohttp.ClientError as e:
            logger.warning(
                f'[AutomationEventService] HTTP error forwarding to automation service: {e}'
            )
