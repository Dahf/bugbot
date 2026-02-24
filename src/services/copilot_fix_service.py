"""Copilot coding agent fix service -- delegates code fixes to GitHub Copilot."""

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

# Copilot agent bot username on GitHub
COPILOT_BOT = "copilot-swe-agent[bot]"

GITHUB_API = "https://api.github.com"


class CopilotFixService:
    """Code fix service that delegates to GitHub Copilot's coding agent.

    Uses a GitHub PAT (not the App installation token) to:
    1. Create a GitHub issue from the bug report
    2. Assign ``copilot-swe-agent[bot]`` with custom instructions
    3. Poll for a PR created by Copilot
    4. Return a result dict compatible with ``CodeFixService.generate_fix()``

    The PAT must have ``repo`` scope.
    """

    def __init__(
        self,
        github_pat: str,
        session_timeout: int = 3600,
    ) -> None:
        self._pat = github_pat
        self._session_timeout = session_timeout
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # HTTP session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-init aiohttp session with PAT auth headers."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"token {self._pat}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------------------

    async def _create_issue(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        bug: dict,
    ) -> dict:
        """Create a GitHub issue from the bug report.

        Returns ``{"number": int, "html_url": str, "node_id": str}``.
        """
        title = (
            f"[Bug #{bug.get('hash_id', '?')}] "
            f"{bug.get('title', 'Bug fix')}"
        )
        body = self._build_issue_body(bug)

        url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
        async with session.post(url, json={
            "title": title,
            "body": body,
            "labels": ["bot-created"],
        }) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return {
                "number": data["number"],
                "html_url": data["html_url"],
                "node_id": data["node_id"],
            }

    async def _assign_copilot_rest(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        issue_number: int,
        base_branch: str,
        custom_instructions: str,
    ) -> bool:
        """Assign Copilot via REST API.

        Returns True on success, False on 422 (caller should try GraphQL).
        """
        url = (
            f"{GITHUB_API}/repos/{owner}/{repo}"
            f"/issues/{issue_number}/assignees"
        )
        payload = {
            "assignees": [COPILOT_BOT],
            "agent_assignment": {
                "target_repo": f"{owner}/{repo}",
                "base_branch": base_branch,
                "custom_instructions": custom_instructions,
            },
        }
        async with session.post(url, json=payload) as resp:
            if resp.status == 422:
                logger.warning(
                    "REST Copilot assignment returned 422 for %s/%s#%d",
                    owner, repo, issue_number,
                )
                return False
            resp.raise_for_status()
            return True

    async def _assign_copilot_graphql(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        issue_node_id: str,
    ) -> None:
        """Assign Copilot via GraphQL (fallback when REST returns 422).

        Uses ``replaceActorsForAssignable`` with the special
        ``GraphQL-Features`` header required for Copilot assignment.
        """
        # Resolve copilot-swe-agent[bot] node ID
        user_url = f"{GITHUB_API}/users/{COPILOT_BOT}"
        async with session.get(user_url) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Cannot resolve {COPILOT_BOT} node ID "
                    f"(HTTP {resp.status}). Is Copilot enabled for "
                    f"{owner}/{repo}?"
                )
            bot_node_id = (await resp.json())["node_id"]

        mutation = """
        mutation($assignableId: ID!, $actorIds: [ID!]!) {
            replaceActorsForAssignable(input: {
                assignableId: $assignableId,
                actorIds: $actorIds
            }) {
                assignable { ... on Issue { id } }
            }
        }
        """
        headers = {
            "GraphQL-Features": (
                "issues_copilot_assignment_api_support,"
                "coding_agent_model_selection"
            ),
        }
        async with session.post(
            f"{GITHUB_API}/graphql",
            json={
                "query": mutation,
                "variables": {
                    "assignableId": issue_node_id,
                    "actorIds": [bot_node_id],
                },
            },
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if "errors" in data:
                raise RuntimeError(f"GraphQL assignment errors: {data['errors']}")

    async def _poll_for_pr(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        issue_number: int,
        timeout: int,
        poll_interval: int = 30,
        progress_callback=None,
    ) -> dict | None:
        """Poll for a PR created by Copilot.

        Copilot creates branches prefixed with ``copilot/``.
        Returns a PR dict or None on timeout.
        """
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            url = (
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
                f"?state=open&sort=created&direction=desc&per_page=10"
            )
            async with session.get(url) as resp:
                resp.raise_for_status()
                prs = await resp.json()

            for pr in prs:
                author = pr.get("user", {}).get("login", "")
                head_ref = pr.get("head", {}).get("ref", "")
                body = pr.get("body", "") or ""
                # Match by author + branch prefix, and optionally issue ref
                if (
                    author == COPILOT_BOT
                    and head_ref.startswith("copilot/")
                    and (
                        f"#{issue_number}" in body
                        or f"#{issue_number}" in pr.get("title", "")
                    )
                ):
                    return {
                        "number": pr["number"],
                        "html_url": pr["html_url"],
                        "title": pr["title"],
                        "branch": head_ref,
                    }

            if progress_callback:
                minutes, seconds = divmod(elapsed, 60)
                try:
                    await progress_callback(
                        f"Waiting for Copilot PR... ({minutes}m {seconds}s)"
                    )
                except Exception:
                    pass

        return None

    # ------------------------------------------------------------------
    # Prompt / instruction builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_issue_body(bug: dict) -> str:
        """Build the GitHub issue body from bug data."""
        return (
            f"## Bug Report #{bug.get('hash_id', 'unknown')}\n\n"
            f"**Title:** {bug.get('title', 'Unknown bug')}\n"
            f"**Description:** {bug.get('description', 'No description')}\n"
            f"**Severity:** {bug.get('severity', 'unknown')}\n\n"
            f"### Steps to Reproduce\n"
            f"{bug.get('steps_to_reproduce', 'Not provided')}\n\n"
            f"### AI Analysis\n"
            f"- **Root Cause:** {bug.get('ai_root_cause', 'Not analyzed')}\n"
            f"- **Affected Area:** {bug.get('ai_affected_area', 'Not identified')}\n"
            f"- **Suggested Fix:** {bug.get('ai_suggested_fix', 'No suggestion')}\n\n"
            f"---\n"
            f"*Created by BugBot for Copilot coding agent*"
        )

    @staticmethod
    def _build_custom_instructions(
        bug: dict, relevant_paths: list[str]
    ) -> str:
        """Build custom instructions for the ``agent_assignment`` payload."""
        parts = [
            "Fix the bug described in this issue.",
            f"Root cause: {bug.get('ai_root_cause', 'See issue body')}.",
            f"Suggested fix: {bug.get('ai_suggested_fix', 'See issue body')}.",
        ]
        if relevant_paths:
            parts.append(f"Relevant files: {', '.join(relevant_paths)}.")
        parts.append("Keep changes minimal and focused on the reported bug.")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Main entry point (same signature as CodeFixService.generate_fix)
    # ------------------------------------------------------------------

    async def generate_fix(
        self,
        github_service,
        owner: str,
        repo: str,
        branch: str,
        bug: dict,
        relevant_paths: list[str],
        progress_callback=None,
    ) -> dict:
        """Delegate code fix to GitHub Copilot coding agent.

        Returns a result dict compatible with ``CodeFixService``.
        """

        async def _progress(msg: str) -> None:
            logger.info("CopilotFix progress: %s", msg)
            if progress_callback:
                try:
                    await progress_callback(msg)
                except Exception as exc:
                    logger.warning("Progress callback failed: %s", exc)

        process_log: dict = {
            "files_explored": relevant_paths,
            "rounds": [],
            "total_tokens": {"input": 0, "output": 0},
        }

        try:
            session = await self._get_session()

            # 1. Get default branch
            await _progress("Getting default branch info...")
            default_branch, _ = await github_service.get_default_branch_sha(
                owner, repo
            )

            # 2. Create issue
            await _progress("Creating GitHub issue for Copilot agent...")
            issue = await self._create_issue(session, owner, repo, bug)
            issue_number = issue["number"]
            process_log["copilot_issue"] = issue_number
            await _progress(
                f"Issue #{issue_number} created: {issue['html_url']}"
            )

            # 3. Build instructions
            instructions = self._build_custom_instructions(
                bug, relevant_paths
            )

            # 4. Assign Copilot (REST, with GraphQL fallback)
            await _progress("Assigning Copilot coding agent...")
            rest_ok = await self._assign_copilot_rest(
                session, owner, repo, issue_number,
                default_branch, instructions,
            )
            if not rest_ok:
                await _progress(
                    "REST assignment returned 422, trying GraphQL..."
                )
                await self._assign_copilot_graphql(
                    session, owner, repo, issue["node_id"]
                )
            await _progress("Copilot agent assigned. Waiting for PR...")

            # 5. Poll for PR
            pr = await self._poll_for_pr(
                session, owner, repo, issue_number,
                timeout=self._session_timeout,
                progress_callback=progress_callback,
            )

            if pr is None:
                minutes = self._session_timeout // 60
                return {
                    "success": False,
                    "error": (
                        f"Copilot did not create a PR within {minutes} minutes"
                    ),
                    "process_log": process_log,
                }

            await _progress(f"Copilot PR found: {pr['html_url']}")
            process_log["copilot_pr"] = pr["number"]

            return {
                "success": True,
                "changed_files": {},
                "process_log": process_log,
                "rounds_taken": 1,
                "validation_passed": True,
                "commit_sha": None,
                "copilot_pr": pr,
            }

        except Exception as exc:
            logger.exception("Copilot fix generation failed: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "process_log": process_log,
            }
