"""GitHub App API service with installation auth and rate limit handling."""

import asyncio
import base64
import logging
import re

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

    async def ensure_labels(
        self,
        owner: str,
        repo: str,
        labels: list[tuple[str, str]],
    ) -> None:
        """Create labels in the repo if they don't already exist.

        *labels* is a list of (name, hex_color) tuples.  A 422 response
        means the label already exists -- that's expected and ignored.
        """
        gh = await self.get_installation_client(owner, repo)
        for name, color in labels:
            try:
                await gh.rest.issues.async_create_label(
                    owner, repo, name=name, color=color
                )
                logger.info("Created label %r in %s/%s", name, owner, repo)
            except Exception:
                # 422 = label already exists -- that's fine
                pass

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict:
        """Create a GitHub issue and return its number, URL, and title.

        Returns a dict with ``number``, ``html_url``, and ``title`` keys.
        """
        gh = await self.get_installation_client(owner, repo)
        resp = await gh.rest.issues.async_create(
            owner, repo, title=title, body=body, labels=labels
        )
        issue = resp.parsed_data
        return {
            "number": issue.number,
            "html_url": issue.html_url,
            "title": issue.title,
        }

    # ------------------------------------------------------------------
    # Branch & PR operations (Plan 03)
    # ------------------------------------------------------------------

    async def get_default_branch_sha(
        self, owner: str, repo: str
    ) -> tuple[str, str]:
        """Return ``(default_branch, sha)`` for the repo's default branch.

        Uses the installation client to fetch repo info and the HEAD ref.
        """
        gh = await self.get_installation_client(owner, repo)
        repo_resp = await gh.rest.repos.async_get(owner, repo)
        default_branch = repo_resp.parsed_data.default_branch
        ref_resp = await gh.rest.git.async_get_ref(
            owner, repo, f"heads/{default_branch}"
        )
        sha = ref_resp.parsed_data.object_.sha
        return (default_branch, sha)

    async def get_target_branch_sha(
        self, owner: str, repo: str, app_version: str | None
    ) -> tuple[str, str]:
        """Return ``(branch, sha)`` for the version branch if it exists,
        otherwise fall back to the default branch.

        Tries ``v{app_version}`` first (e.g. ``v1.0.1``).
        """
        if app_version:
            version_branch = f"v{app_version}"
            gh = await self.get_installation_client(owner, repo)
            try:
                ref_resp = await gh.rest.git.async_get_ref(
                    owner, repo, f"heads/{version_branch}"
                )
                sha = ref_resp.parsed_data.object_.sha
                logger.info(
                    "Using version branch %s for %s/%s",
                    version_branch, owner, repo,
                )
                return (version_branch, sha)
            except Exception:
                logger.info(
                    "Version branch %s not found in %s/%s, using default",
                    version_branch, owner, repo,
                )
        return await self.get_default_branch_sha(owner, repo)

    async def create_branch(
        self, owner: str, repo: str, branch_name: str, base_sha: str
    ) -> None:
        """Create a feature branch from *base_sha*.

        GH-08: This ALWAYS creates a new branch -- never touches the
        default branch.
        """
        gh = await self.get_installation_client(owner, repo)
        await gh.rest.git.async_create_ref(
            owner, repo, ref=f"refs/heads/{branch_name}", sha=base_sha
        )
        logger.info(
            "Created branch %s in %s/%s from %s",
            branch_name, owner, repo, base_sha[:8],
        )

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        """Create a pull request and return its ``number``, ``html_url``, ``title``."""
        gh = await self.get_installation_client(owner, repo)
        resp = await gh.rest.pulls.async_create(
            owner, repo, title=title, head=head, base=base, body=body
        )
        pr = resp.parsed_data
        return {
            "number": pr.number,
            "html_url": pr.html_url,
            "title": pr.title,
        }

    async def delete_branch(
        self, owner: str, repo: str, branch_name: str
    ) -> None:
        """Delete a branch, silently ignoring 404/422 (already gone)."""
        gh = await self.get_installation_client(owner, repo)
        try:
            await gh.rest.git.async_delete_ref(
                owner, repo, f"heads/{branch_name}"
            )
            logger.info(
                "Deleted branch %s in %s/%s", branch_name, owner, repo
            )
        except Exception:
            # 404 or 422 -- branch already deleted or doesn't exist
            logger.debug(
                "Branch %s in %s/%s already deleted or not found",
                branch_name, owner, repo,
            )

    # ------------------------------------------------------------------
    # Source file reading & context commit operations (Plan 04)
    # ------------------------------------------------------------------

    # Allowed source code extensions for identify_relevant_files
    _SOURCE_EXTENSIONS = frozenset({
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".swift",
        ".dart", ".go", ".rs", ".c", ".cpp", ".h", ".rb", ".php",
        ".cs", ".vue", ".svelte",
    })

    _MAX_FILE_SIZE = 50 * 1024  # 50 KB

    async def read_repo_files(
        self,
        owner: str,
        repo: str,
        file_paths: list[str],
        ref: str | None = None,
    ) -> list[dict]:
        """Read files from a GitHub repo and return their decoded contents.

        For each path, fetches the file via the Contents API, base64-decodes
        the content, and returns a list of dicts with ``path``, ``content``,
        ``size``, and ``truncated`` keys.  Files that are larger than 50 KB
        are truncated.  Missing or inaccessible files are silently skipped.
        """
        if not file_paths:
            return []

        gh = await self.get_installation_client(owner, repo)
        results: list[dict] = []

        for path in file_paths:
            try:
                kwargs: dict = {"owner": owner, "repo": repo, "path": path}
                if ref:
                    kwargs["ref"] = ref
                resp = await gh.rest.repos.async_get_content(**kwargs)
                data = resp.parsed_data

                # async_get_content returns a union; file objects have .content
                raw_content: str = data.content  # type: ignore[union-attr]
                decoded = base64.b64decode(raw_content).decode("utf-8")
                file_size = len(decoded.encode("utf-8"))
                truncated = file_size > self._MAX_FILE_SIZE

                if truncated:
                    decoded = decoded[: self._MAX_FILE_SIZE]

                results.append({
                    "path": path,
                    "content": decoded,
                    "size": file_size,
                    "truncated": truncated,
                })
            except Exception as exc:
                logger.warning(
                    "Could not read %s from %s/%s: %s", path, owner, repo, exc
                )
                continue

        return results

    async def commit_context_file(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        file_path: str,
        content: str,
        message: str,
    ) -> None:
        """Commit a single file to an existing branch.

        The file content is base64-encoded before sending to the API.
        This writes to the feature branch only -- never the default branch
        (GH-08 preserved).
        """
        gh = await self.get_installation_client(owner, repo)
        b64_content = base64.b64encode(content.encode("utf-8")).decode("ascii")

        await gh.rest.repos.async_create_or_update_file_contents(
            owner,
            repo,
            file_path,
            message=message,
            content=b64_content,
            branch=branch_name,
        )
        logger.info(
            "Committed %s to branch %s in %s/%s",
            file_path, branch_name, owner, repo,
        )

    async def identify_relevant_files(
        self,
        owner: str,
        repo: str,
        ai_affected_area: str,
        ref: str | None = None,
    ) -> list[str]:
        """Identify source files relevant to an AI-identified affected area.

        Uses the repo's file tree and keyword overlap scoring to return
        up to 5 likely-relevant file paths, sorted by relevance.  This is
        a simple heuristic -- not full RAG indexing.
        """
        if not ai_affected_area:
            return []

        gh = await self.get_installation_client(owner, repo)
        tree_resp = await gh.rest.git.async_get_tree(
            owner, repo, ref or "HEAD", recursive="true"
        )
        tree = tree_resp.parsed_data.tree

        # Build keyword set from the affected area description
        keywords = set(ai_affected_area.lower().split())

        scored: list[tuple[str, int]] = []
        for item in tree:
            # Skip directories and non-source files
            if item.type != "blob":
                continue
            path: str = item.path
            # Check extension
            dot_idx = path.rfind(".")
            if dot_idx == -1:
                continue
            ext = path[dot_idx:]
            if ext not in self._SOURCE_EXTENSIONS:
                continue

            # Score by keyword overlap with full lowercase path
            path_lower = path.lower()
            score = sum(1 for kw in keywords if kw in path_lower)
            if score > 0:
                scored.append((path, score))

        # Sort by score descending, take top 5
        scored.sort(key=lambda t: t[1], reverse=True)
        return [path for path, _ in scored[:5]]

    @staticmethod
    def build_branch_name(hash_id: str, title: str) -> str:
        """Build a branch name in the format ``bot/bug-{id}-{slug}``.

        Slugifies the title: lowercase, replaces non-alphanumeric with
        hyphens, collapses consecutive hyphens, strips leading/trailing
        hyphens, and truncates to 30 characters.
        """
        slug = title.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = re.sub(r"-{2,}", "-", slug)
        slug = slug.strip("-")[:30].rstrip("-")
        return f"bot/bug-{hash_id}-{slug}"

    # ------------------------------------------------------------------
    # Atomic multi-file commit & CI polling (Plan 05-01)
    # ------------------------------------------------------------------

    async def commit_files_atomic(
        self,
        owner: str,
        repo: str,
        branch: str,
        changed_files: dict[str, str],
        commit_message: str,
    ) -> str:
        """Commit multiple file changes as a single atomic commit.

        Uses the Git Data API (blobs, trees, commits, refs) to create one
        commit containing all file changes -- avoids the one-commit-per-file
        limitation of the Contents API.

        *changed_files* maps relative file paths to their full content.
        Returns the SHA of the new commit.
        """
        gh = await self.get_installation_client(owner, repo)

        # 1. Create blobs for each changed file
        tree_items: list[dict] = []
        for path, content in changed_files.items():
            blob_resp = await gh.rest.git.async_create_blob(
                owner, repo, content=content, encoding="utf-8"
            )
            tree_items.append({
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp.parsed_data.sha,
            })

        # 2. Get current branch HEAD SHA
        ref_resp = await gh.rest.git.async_get_ref(
            owner, repo, f"heads/{branch}"
        )
        head_sha = ref_resp.parsed_data.object_.sha

        # 3. Get current commit's tree SHA (base tree)
        commit_resp = await gh.rest.git.async_get_commit(owner, repo, head_sha)
        base_tree_sha = commit_resp.parsed_data.tree.sha

        # 4. Create new tree with file changes
        tree_resp = await gh.rest.git.async_create_tree(
            owner, repo, tree=tree_items, base_tree=base_tree_sha
        )

        # 5. Create commit
        new_commit_resp = await gh.rest.git.async_create_commit(
            owner, repo,
            tree=tree_resp.parsed_data.sha,
            message=commit_message,
            parents=[head_sha],
        )
        new_commit_sha = new_commit_resp.parsed_data.sha

        # 6. Update branch ref to point to new commit
        await gh.rest.git.async_update_ref(
            owner, repo, f"heads/{branch}", sha=new_commit_sha
        )

        logger.info(
            "Atomic commit %s on %s/%s branch %s (%d files)",
            new_commit_sha[:8], owner, repo, branch, len(changed_files),
        )
        return new_commit_sha

    async def poll_ci_status(
        self,
        owner: str,
        repo: str,
        ref: str,
        timeout: int = 300,
        poll_interval: int = 15,
        initial_delay: int = 15,
    ) -> dict:
        """Poll GitHub Checks API until all check runs complete or timeout.

        Waits *initial_delay* seconds before the first poll (allows GitHub
        Actions to register check runs after a push).

        Returns a dict with ``status`` and ``details`` keys:
        - ``{"status": "passed", "details": "All N checks passed"}``
        - ``{"status": "failed", "details": "- name: conclusion\\n..."}``
        - ``{"status": "no_ci", "details": "No CI pipeline detected"}``
        - ``{"status": "timeout", "details": "CI did not complete within Ns"}``
        """
        gh = await self.get_installation_client(owner, repo)

        # Initial delay to let GitHub Actions register check runs
        await asyncio.sleep(initial_delay)

        elapsed = 0
        first_poll = True
        while elapsed < timeout:
            resp = await gh.rest.checks.async_list_for_ref(owner, repo, ref)
            check_runs = resp.parsed_data.check_runs
            total = resp.parsed_data.total_count

            if total == 0:
                if first_poll:
                    # Second chance: wait one more interval and retry
                    first_poll = False
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                    continue
                return {
                    "status": "no_ci",
                    "details": "No CI pipeline detected",
                }

            first_poll = False

            all_complete = all(
                cr.status == "completed" for cr in check_runs
            )
            if all_complete:
                failures = [
                    cr for cr in check_runs
                    if cr.conclusion not in ("success", "neutral", "skipped")
                ]
                if failures:
                    details = "\n".join(
                        f"- {cr.name}: {cr.conclusion}" for cr in failures
                    )
                    return {"status": "failed", "details": details}
                return {
                    "status": "passed",
                    "details": f"All {total} checks passed",
                }

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return {
            "status": "timeout",
            "details": f"CI did not complete within {timeout}s",
        }

    async def get_installation_token(self, owner: str, repo: str) -> str:
        """Get a raw installation access token for git CLI operations.

        Returns a token string suitable for use in git clone URLs:
        ``https://x-access-token:{token}@github.com/owner/repo.git``

        The token is short-lived (~1 hour). Get a fresh token immediately
        before any git CLI operation.
        """
        # Get the installation ID for this repo
        resp = await self.app_github.rest.apps.async_get_repo_installation(
            owner, repo
        )
        installation_id = resp.parsed_data.id

        # Create an installation access token
        token_resp = (
            await self.app_github.rest.apps
            .async_create_installation_access_token(installation_id)
        )
        return token_resp.parsed_data.token

    async def close(self) -> None:
        """Close the underlying HTTP client for clean shutdown."""
        await self.app_github.aclose()
