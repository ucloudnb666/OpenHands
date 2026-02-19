from openhands.integrations.bitbucket_data_center.service.base import (
    BitbucketDCMixinBase,
)
from openhands.integrations.service_types import Branch, PaginatedBranchesResponse


class BitbucketDCBranchesMixin(BitbucketDCMixinBase):
    """
    Mixin for Bitbucket Data Center branch-related operations.
    Uses /projects/{key}/repos/{slug}/branches endpoints.
    Branch name comes from 'displayId', commit SHA from 'latestCommit'.
    """

    async def get_branches(self, repository: str) -> list[Branch]:
        """Get branches for a repository."""
        project, repo_slug = self._extract_owner_and_repo(repository)
        url = f'{self.BASE_URL}/projects/{project}/repos/{repo_slug}/branches'

        MAX_BRANCHES = 1000
        PER_PAGE = 100

        params = {
            'limit': PER_PAGE,
            'orderBy': 'MODIFICATION',
        }

        branch_data = await self._fetch_paginated_data(url, params, MAX_BRANCHES)

        branches = []
        for branch in branch_data:
            branches.append(
                Branch(
                    name=branch.get('displayId', ''),
                    commit_sha=branch.get('latestCommit', ''),
                    protected=False,
                    last_push_date=None,
                )
            )

        return branches

    async def get_paginated_branches(
        self, repository: str, page: int = 1, per_page: int = 30
    ) -> PaginatedBranchesResponse:
        """Get branches for a repository with pagination."""
        project, repo_slug = self._extract_owner_and_repo(repository)
        url = f'{self.BASE_URL}/projects/{project}/repos/{repo_slug}/branches'

        start = (page - 1) * per_page
        params = {
            'start': start,
            'limit': per_page,
            'orderBy': 'MODIFICATION',
        }

        response, _ = await self._make_request(url, params)

        branches = []
        for branch in response.get('values', []):
            branches.append(
                Branch(
                    name=branch.get('displayId', ''),
                    commit_sha=branch.get('latestCommit', ''),
                    protected=False,
                    last_push_date=None,
                )
            )

        has_next_page = not response.get('isLastPage', True)
        total_count = response.get('size')

        return PaginatedBranchesResponse(
            branches=branches,
            has_next_page=has_next_page,
            current_page=page,
            per_page=per_page,
            total_count=total_count,
        )

    async def search_branches(
        self, repository: str, query: str, per_page: int = 30
    ) -> list[Branch]:
        """Search branches by name using filterText param."""
        project, repo_slug = self._extract_owner_and_repo(repository)
        url = f'{self.BASE_URL}/projects/{project}/repos/{repo_slug}/branches'

        params = {
            'limit': per_page,
            'filterText': query,
            'orderBy': 'MODIFICATION',
        }

        response, _ = await self._make_request(url, params)

        branches: list[Branch] = []
        for branch in response.get('values', []):
            branches.append(
                Branch(
                    name=branch.get('displayId', ''),
                    commit_sha=branch.get('latestCommit', ''),
                    protected=False,
                    last_push_date=None,
                )
            )

        return branches
