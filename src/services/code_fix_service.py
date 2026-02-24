"""Agentic AI code fix service using Claude tool_runner for multi-step code generation."""

import asyncio
import logging
import os
import shutil
import stat
import tempfile
from pathlib import Path

from anthropic import AsyncAnthropic, beta_async_tool

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Tool factory -- creates tool functions with closure over clone_dir
# ------------------------------------------------------------------


def _create_tools(clone_dir: Path, max_files: int):
    """Create agentic tool functions bound to a specific clone directory.

    Returns ``(tools, changed_files, files_read_count)`` where:
    - *tools* is a list of decorated tool functions for the tool_runner
    - *changed_files* is a set of relative paths that were written
    - *files_read_count* is a single-element list tracking reads (mutable closure)
    """
    changed_files: set[str] = set()
    files_read_count: list[int] = [0]

    @beta_async_tool
    async def read_file(path: str) -> str:
        """Read a source file from the cloned repository.

        Args:
            path: Relative file path from repo root (e.g., 'src/main.py')
        """
        if files_read_count[0] >= max_files:
            return f"ERROR: File read limit ({max_files}) reached. Work with files already read."

        full_path = (clone_dir / path).resolve()

        # Security: no path traversal outside clone_dir
        try:
            full_path.relative_to(clone_dir.resolve())
        except ValueError:
            return f"ERROR: Path traversal not allowed: {path}"

        if not full_path.exists():
            return f"ERROR: File not found: {path}"
        if not full_path.is_file():
            return f"ERROR: Not a file: {path}"

        content = full_path.read_text(encoding="utf-8", errors="replace")
        files_read_count[0] += 1

        # Truncate large files
        lines = content.splitlines()
        if len(lines) > 500:
            content = "\n".join(lines[:500]) + f"\n\n... truncated ({len(lines)} total lines)"

        return content

    @beta_async_tool
    async def write_file(path: str, content: str) -> str:
        """Write or modify a file in the working copy. This stages the change for the final commit.

        Args:
            path: Relative file path from repo root
            content: Complete file content (not a diff -- write the full file)
        """
        full_path = (clone_dir / path).resolve()

        # Security: no path traversal outside clone_dir
        try:
            full_path.relative_to(clone_dir.resolve())
        except ValueError:
            return f"ERROR: Path traversal not allowed: {path}"

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        changed_files.add(path)
        return f"Written {len(content)} bytes to {path}"

    @beta_async_tool
    async def search_in_repo(query: str, file_pattern: str = "*") -> str:
        """Search for text across repository files using grep.

        Args:
            query: Text to search for (case-insensitive)
            file_pattern: Glob pattern for files to search (default: all files)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "grep", "-rn", "-i", "--include", file_pattern,
                query, str(clone_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
            output = (stdout or b"").decode("utf-8", errors="replace")[:5000]
            if not output.strip():
                return "No matches found."
            return output
        except asyncio.TimeoutError:
            return "ERROR: Search timed out after 30 seconds."
        except FileNotFoundError:
            return "ERROR: grep not available on this system."

    @beta_async_tool
    async def list_directory(path: str = ".") -> str:
        """List files and directories at the given path in the repository.

        Args:
            path: Relative directory path from repo root (default: root)
        """
        target = (clone_dir / path).resolve()

        # Security: no path traversal outside clone_dir
        try:
            target.relative_to(clone_dir.resolve())
        except ValueError:
            return f"ERROR: Path traversal not allowed: {path}"

        if not target.is_dir():
            return f"ERROR: Not a directory: {path}"

        entries = sorted(target.iterdir())
        result = []
        for entry in entries[:100]:
            try:
                rel = entry.relative_to(clone_dir)
            except ValueError:
                continue
            prefix = "d " if entry.is_dir() else "f "
            result.append(prefix + str(rel).replace("\\", "/"))
        return "\n".join(result) if result else "(empty directory)"

    return [read_file, write_file, search_in_repo, list_directory], changed_files, files_read_count


class CodeFixService:
    """Agentic code fix orchestrator using Claude tool_runner.

    Clones a repo, lets Claude explore and fix code via tool use,
    validates through lint/self-review/CI quality gates, and
    produces atomic commits.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4096,
        max_rounds: int = 3,
        max_files: int = 15,
        ci_timeout: int = 300,
    ) -> None:
        self.client = AsyncAnthropic(
            api_key=api_key,
            timeout=120.0,
            max_retries=2,
        )
        self.model = model
        self.max_tokens = max_tokens
        self.max_rounds = max_rounds
        self.max_files = max_files
        self.ci_timeout = ci_timeout

    # ------------------------------------------------------------------
    # Clone management
    # ------------------------------------------------------------------

    async def clone_repo(
        self, owner: str, repo: str, branch: str, token: str
    ) -> Path:
        """Shallow-clone a repo into a temp directory.

        Returns the clone directory Path. On failure, cleans up the
        temp dir and raises RuntimeError.
        """
        clone_dir = Path(
            tempfile.mkdtemp(prefix=f"bugbot-{owner}-{repo}-")
        )
        clone_url = (
            f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "--branch", branch,
                clone_url, str(clone_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"git clone failed (exit {proc.returncode}): "
                    f"{(stderr or b'').decode('utf-8', errors='replace')}"
                )
        except Exception:
            self.cleanup_clone(clone_dir)
            raise

        logger.info(
            "Cloned %s/%s branch %s to %s", owner, repo, branch, clone_dir
        )
        return clone_dir

    def cleanup_clone(self, clone_dir: Path) -> None:
        """Remove the temporary clone directory.

        Handles Windows read-only ``.git`` files by making them
        writable before deletion (Pitfall 3 from research).
        """
        def _on_rm_error(func, path, exc_info):
            """Make read-only files writable and retry removal."""
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                logger.warning("Could not remove %s during cleanup", path)

        try:
            shutil.rmtree(str(clone_dir), onerror=_on_rm_error)
            logger.info("Cleaned up clone dir %s", clone_dir)
        except Exception as exc:
            logger.warning("Clone cleanup failed for %s: %s", clone_dir, exc)

    # ------------------------------------------------------------------
    # System prompt builder
    # ------------------------------------------------------------------

    def _build_code_fix_prompt(
        self, bug: dict, relevant_paths: list[str]
    ) -> str:
        """Build the system prompt for the code fix generation round."""
        hash_id = bug.get("hash_id", "unknown")
        title = bug.get("title", "Unknown bug")
        description = bug.get("description", "No description provided.")
        severity = bug.get("severity", "unknown")
        steps = bug.get("steps_to_reproduce", "Not provided.")
        root_cause = bug.get("ai_root_cause", "Not analyzed.")
        affected_area = bug.get("ai_affected_area", "Not identified.")
        suggested_fix = bug.get("ai_suggested_fix", "No suggestion.")

        paths_section = ""
        if relevant_paths:
            paths_list = "\n".join(f"  - {p}" for p in relevant_paths)
            paths_section = (
                f"\n\nRelevant files identified (start by reading these):\n"
                f"{paths_list}"
            )

        return (
            f"You are a senior software developer fixing a bug in a codebase.\n"
            f"\n"
            f"Bug Report #{hash_id}\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Severity: {severity}\n"
            f"Steps to Reproduce: {steps}\n"
            f"\n"
            f"AI Analysis:\n"
            f"  Root Cause: {root_cause}\n"
            f"  Affected Area: {affected_area}\n"
            f"  Suggested Fix: {suggested_fix}\n"
            f"{paths_section}\n"
            f"\n"
            f"Instructions:\n"
            f"1. Read the relevant files to understand the codebase.\n"
            f"2. Explore related files if needed (follow imports, check tests).\n"
            f"3. Write the fix using write_file -- provide the COMPLETE file content.\n"
            f"4. Keep changes minimal and focused on the reported bug.\n"
            f"5. Preserve existing code style and conventions.\n"
            f"\n"
            f"When done, return a brief summary of what you changed and why."
        )

    # ------------------------------------------------------------------
    # Single agentic generation round
    # ------------------------------------------------------------------

    async def _run_generation_round(
        self,
        bug: dict,
        clone_dir: Path,
        tools: list,
        round_number: int,
        feedback: dict | None = None,
        relevant_paths: list[str] | None = None,
    ) -> dict:
        """Run a single round of agentic code generation via tool_runner.

        For round 1, uses the full system prompt with bug context.
        For subsequent rounds, includes feedback from the previous round's
        quality gates and asks Claude to address the issues.

        Returns ``{"message": final_message, "usage": {"input_tokens": ..., "output_tokens": ...}}``.
        """
        if round_number == 1:
            prompt = self._build_code_fix_prompt(bug, relevant_paths or [])
            messages = [{"role": "user", "content": prompt}]
        else:
            # Build feedback message for iteration rounds
            feedback_text = self._build_feedback_prompt(feedback)
            messages = [
                {
                    "role": "user",
                    "content": feedback_text,
                },
            ]

        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=self.max_tokens,
            tools=tools,
            messages=messages,
        )
        final_message = await runner.until_done()

        # Extract token usage
        usage = {
            "input_tokens": final_message.usage.input_tokens,
            "output_tokens": final_message.usage.output_tokens,
        }

        return {"message": final_message, "usage": usage}

    def _build_feedback_prompt(self, feedback: dict | None) -> str:
        """Build a feedback prompt for subsequent generation rounds."""
        if not feedback:
            return "Please review your changes and ensure they are correct."

        feedback_type = feedback.get("type", "unknown")

        if feedback_type == "lint":
            output = feedback.get("output", "No details available.")
            return (
                f"The previous fix had lint errors. Please fix them.\n\n"
                f"Lint output:\n```\n{output}\n```\n\n"
                f"Read the affected files, fix the lint issues, and write "
                f"the corrected files. Keep changes minimal."
            )
        elif feedback_type == "self_review":
            issues = feedback.get("issues", [])
            issues_text = "\n".join(f"  - {issue}" for issue in issues)
            return (
                f"The AI self-review found issues with your fix:\n"
                f"{issues_text}\n\n"
                f"Please address these issues. Read the affected files, "
                f"apply corrections, and write the updated files."
            )
        elif feedback_type == "ci":
            details = feedback.get("details", "No details available.")
            return (
                f"CI checks failed after your fix was committed:\n\n"
                f"{details}\n\n"
                f"Please read the affected files, diagnose the failures, "
                f"and write corrected versions."
            )
        else:
            return "Please review and improve your previous changes."
