"""GitHub App API service with installation auth and rate limit handling."""

import logging

from githubkit import GitHub, AppAuthStrategy
from githubkit.retry import RetryChainDecision, RetryRateLimit, RetryServerError

logger = logging.getLogger(__name__)


class GitHubService:
    """Wraps githubkit with App-level auth and automatic rate limit retry.

    Handles GH-09: rate limits are retried automatically via
    ``RetryChainDecision(RetryRateLimit, RetryServerError)``.
    """

    def __init__(
        self,
        app_id: str,
        private_key: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self.app_github = GitHub(
            AppAuthStrategy(
                app_id=app_id,
                private_key=private_key,
                client_id=client_id,
                client_secret=client_secret,
            ),
            auto_retry=RetryChainDecision(
                RetryRateLimit(max_retry=3),
                RetryServerError(max_retry=2),
            ),
        )

    async def get_installation_client(self, owner: str, repo: str) -> GitHub:
        """Return an installation-scoped client for a specific repo.

        This is the gateway for ALL repo-scoped operations. The returned
        client authenticates with an auto-rotating installation token.
        """
        resp = await self.app_github.rest.apps.async_get_repo_installation(
            owner, repo
        )
        installation = resp.parsed_data
        return self.app_github.with_auth(
            self.app_github.auth.as_installation(installation.id)
        )

    async def list_installations(self) -> list:
        """List all installations for this GitHub App.

        Used by the /init command to detect new installations via polling.
        """
        resp = await self.app_github.rest.apps.async_list_installations()
        return resp.parsed_data

    async def list_installation_repos(self, installation_id: int) -> list[dict]:
        """List repositories accessible to a specific installation.

        Returns a list of dicts with 'owner' and 'name' keys.
        """
        gh = self.app_github.with_auth(
            self.app_github.auth.as_installation(installation_id)
        )
        resp = await gh.rest.apps.async_list_repos_accessible_to_installation()
        repos = []
        for repo in resp.parsed_data.repositories:
            repos.append({
                "owner": repo.owner.login,
                "name": repo.name,
                "full_name": repo.full_name,
            })
        return repos

    async def close(self) -> None:
        """Close the underlying HTTP client for clean shutdown."""
        await self.app_github.aclose()
