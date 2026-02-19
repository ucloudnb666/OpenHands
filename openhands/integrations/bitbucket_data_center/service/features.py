from openhands.core.logger import openhands_logger as logger
from openhands.integrations.bitbucket_data_center.service.base import (
    BitbucketDCMixinBase,
)
from openhands.integrations.service_types import ResourceNotFoundError
from openhands.microagent.types import MicroagentContentResponse


class BitbucketDCFeaturesMixin(BitbucketDCMixinBase):
    """
    Mixin for Bitbucket Data Center feature operations (microagents, cursor rules, etc.)
    """

    async def get_microagent_content(
        self, repository: str, file_path: str
    ) -> MicroagentContentResponse:
        """Fetch individual file content from Bitbucket Data Center repository.

        Uses the browse endpoint which returns lines as JSON rather than raw text.
        Response shape: {"lines": [{"text": "..."}, ...]}

        Args:
            repository: Repository name in format 'PROJECT/repo_slug'
            file_path: Path to the file within the repository

        Returns:
            MicroagentContentResponse with parsed content and triggers

        Raises:
            ResourceNotFoundError: If file or branch cannot be found
        """
        repo_details = await self.get_repository_details_from_repo_name(repository)

        if not repo_details.main_branch:
            logger.warning(
                f'No main branch found in repository info for {repository}.'
            )
            raise ResourceNotFoundError(
                f'Main branch not found for repository {repository}. '
                f'This repository may be empty or have no default branch configured.'
            )

        project, repo_slug = self._extract_owner_and_repo(repository)
        url = (
            f'{self.BASE_URL}/projects/{project}/repos/{repo_slug}/browse/{file_path}'
            f'?at=refs/heads/{repo_details.main_branch}'
        )

        response, _ = await self._make_request(url)

        # Bitbucket Server browse endpoint returns {"lines": [{"text": "..."}, ...]}
        lines = response.get('lines', [])
        content = '\n'.join(line.get('text', '') for line in lines)

        return self._parse_microagent_content(content, file_path)
