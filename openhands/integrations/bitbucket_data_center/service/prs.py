from openhands.core.logger import openhands_logger as logger
from openhands.integrations.bitbucket_data_center.service.base import (
    BitbucketDCMixinBase,
)
from openhands.integrations.service_types import RequestMethod


class BitbucketDCPRsMixin(BitbucketDCMixinBase):
    """
    Mixin for Bitbucket Data Center pull request operations.
    Uses fromRef/toRef payloads as required by Server REST API 1.0.
    """

    async def create_pr(
        self,
        repo_name: str,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str | None = None,
        draft: bool = False,
    ) -> str:
        """Creates a pull request in Bitbucket Data Center.

        Args:
            repo_name: The repository name in the format "PROJECT/repo_slug"
            source_branch: The source branch name
            target_branch: The target branch name
            title: The title of the pull request
            body: The description of the pull request
            draft: Whether to create a draft pull request (not supported by all versions)

        Returns:
            The URL of the created pull request
        """
        project, repo_slug = self._extract_owner_and_repo(repo_name)
        url = f'{self.BASE_URL}/projects/{project}/repos/{repo_slug}/pull-requests'

        repo_ref = {'slug': repo_slug, 'project': {'key': project}}

        payload = {
            'title': title,
            'description': body or '',
            'fromRef': {
                'id': f'refs/heads/{source_branch}',
                'repository': repo_ref,
            },
            'toRef': {
                'id': f'refs/heads/{target_branch}',
                'repository': repo_ref,
            },
            'reviewers': [],
        }

        data, _ = await self._make_request(
            url=url, params=payload, method=RequestMethod.POST
        )

        # Return the URL to the pull request
        links = data.get('links', {}).get('self', [])
        if links:
            return links[0].get('href', '')
        return ''

    async def get_pr_details(self, repository: str, pr_number: int) -> dict:
        """Get detailed information about a specific pull request.

        Args:
            repository: Repository name in format 'PROJECT/repo_slug'
            pr_number: The pull request ID

        Returns:
            Raw Bitbucket Data Center API response for the pull request
        """
        project, repo_slug = self._extract_owner_and_repo(repository)
        url = f'{self.BASE_URL}/projects/{project}/repos/{repo_slug}/pull-requests/{pr_number}'
        pr_data, _ = await self._make_request(url)
        return pr_data

    async def is_pr_open(self, repository: str, pr_number: int) -> bool:
        """Check if a Bitbucket Data Center pull request is still open.

        Args:
            repository: Repository name in format 'PROJECT/repo_slug'
            pr_number: The PR ID to check

        Returns:
            True if PR is OPEN, False if merged/declined/superseded
        """
        try:
            pr_details = await self.get_pr_details(repository, pr_number)

            if 'state' in pr_details:
                return pr_details['state'] == 'OPEN'

            logger.warning(
                f'Could not determine Bitbucket DC PR status for {repository}#{pr_number}. '
                f'Response keys: {list(pr_details.keys())}. Assuming PR is active.'
            )
            return True

        except Exception as e:
            logger.warning(
                f'Could not determine Bitbucket DC PR status for {repository}#{pr_number}: {e}. '
                f'Including conversation to be safe.'
            )
            return True
