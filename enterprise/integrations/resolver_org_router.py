"""Resolve which OpenHands organization workspace a resolver conversation should be created in.

This module provides a reusable utility for routing resolver conversations
(GitHub, GitLab, Bitbucket, Jira, Slack, etc.) to the correct OpenHands organization
workspace based on claimed Git organizations.
"""

from uuid import UUID

from storage.org_git_claim_store import OrgGitClaimStore
from storage.org_member_store import OrgMemberStore

from openhands.core.logger import openhands_logger as logger

# Known git providers to try when provider is not specified (e.g. Jira case)
KNOWN_PROVIDERS = ['github', 'gitlab', 'bitbucket']


async def resolve_org_for_repo(
    provider: str | None,
    full_repo_name: str,
    keycloak_user_id: str,
) -> UUID | None:
    """Determine the OpenHands org_id for a resolver conversation.

    If the repo's git organization is claimed by an OpenHands org AND the user
    is a member of that org, returns the claiming org's ID. Otherwise returns
    None (caller should fall back to user's personal workspace).

    Args:
        provider: Git provider name ("github", "gitlab", "bitbucket") or None.
                  When None, tries all known providers (used by Jira resolvers
                  where the git provider is not known).
        full_repo_name: Full repository name (e.g., "OpenHands/foo")
        keycloak_user_id: The user's Keycloak UUID string

    Returns:
        The org_id if the repo's org is claimed and user is a member, else None
    """
    git_org = full_repo_name.split('/')[0].lower()

    providers_to_check = [provider] if provider else KNOWN_PROVIDERS

    try:
        claim = None
        for p in providers_to_check:
            claim = await OrgGitClaimStore.get_claim_by_provider_and_git_org(p, git_org)
            if claim:
                break

        if not claim:
            logger.debug(
                f'[OrgResolver] No claim found for {git_org}',
                extra={'providers_checked': providers_to_check},
            )
            return None

        member = await OrgMemberStore.get_org_member(
            claim.org_id, UUID(keycloak_user_id)
        )
        if not member:
            logger.debug(
                f'[OrgResolver] User {keycloak_user_id} is not a member of org '
                f'{claim.org_id} (claimed {git_org}). '
                f'Falling back to personal workspace.',
            )
            return None

        logger.info(
            f'[OrgResolver] Routing conversation to org {claim.org_id} '
            f'for {git_org} (user {keycloak_user_id})',
        )
        return claim.org_id
    except Exception as e:
        logger.error(
            f'[OrgResolver] Error resolving org for {git_org}: {e}',
            exc_info=True,
        )
        return None
