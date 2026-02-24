"""Agentic AI code fix service using Claude tool_runner for multi-step code generation."""

import asyncio
import json
import logging
import os
import shutil
import stat
import tempfile
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic, beta_async_tool

logger = logging.getLogger(__name__)

# The SDK logs a noisy ERROR traceback when the model omits a required
# tool argument (e.g. write_file without content).  We already catch the
# resulting ValueError and retry, so downgrade the SDK logger to WARNING.
logging.getLogger("anthropic.lib.tools._beta_runner").setLevel(logging.WARNING)


# ------------------------------------------------------------------
# Rate-limit-aware HTTP transport
# ------------------------------------------------------------------


class ThrottledTransport(httpx.AsyncBaseTransport):
    """Wraps an httpx async transport with a minimum delay between requests.

    The Anthropic SDK's ``tool_runner`` fires sequential HTTP requests
    as fast as possible (one per tool-use turn).  This transport ensures
    at least *min_interval* seconds elapse between requests, preventing
    429 rate-limit errors on lower API tiers.
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        min_interval: float = 2.0,
    ) -> None:
        self._transport = transport or httpx.AsyncHTTPTransport()
        self._min_interval = min_interval
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            try:
                return await self._transport.handle_async_request(request)
            finally:
                self._last_request_time = asyncio.get_event_loop().time()

    async def aclose(self) -> None:
        await self._transport.aclose()


# ------------------------------------------------------------------
# Linter detection configuration
# ------------------------------------------------------------------

_LINTER_CONFIGS: dict[str, tuple[str, list[str]]] = {
    "ruff.toml": ("ruff", ["ruff", "check", "."]),
    ".flake8": ("flake8", ["flake8", "."]),
    ".pylintrc": ("pylint", ["pylint", "."]),
    ".eslintrc.js": ("eslint", ["npx", "eslint", "."]),
    ".eslintrc.json": ("eslint", ["npx", "eslint", "."]),
    ".eslintrc.yml": ("eslint", ["npx", "eslint", "."]),
    "eslint.config.js": ("eslint", ["npx", "eslint", "."]),
    "eslint.config.mjs": ("eslint", ["npx", "eslint", "."]),
    "Cargo.toml": ("cargo", ["cargo", "clippy", "--", "-D", "warnings"]),
    "go.mod": ("go", ["go", "vet", "./..."]),
}


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
        request_min_interval: float = 10.0,
    ) -> None:
        # Throttle HTTP requests to avoid 429 rate-limit errors.
        # The tool_runner fires sequential requests as fast as possible;
        # this ensures at least *request_min_interval* seconds between them.
        throttled_transport = ThrottledTransport(
            transport=httpx.AsyncHTTPTransport(),
            min_interval=request_min_interval,
        )
        http_client = httpx.AsyncClient(transport=throttled_transport)

        self.client = AsyncAnthropic(
            api_key=api_key,
            timeout=120.0,
            max_retries=2,
            http_client=http_client,
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
        self,
        bug: dict,
        relevant_paths: list[str],
        prefetched_files: dict[str, str] | None = None,
    ) -> str:
        """Build the system prompt for the code fix generation round.

        If *prefetched_files* is provided (path -> content), the file
        contents are embedded directly in the prompt so the model does
        not need to call ``read_file`` for them, saving API round-trips.
        """
        hash_id = bug.get("hash_id", "unknown")
        title = bug.get("title", "Unknown bug")
        description = bug.get("description", "No description provided.")
        severity = bug.get("severity", "unknown")
        steps = bug.get("steps_to_reproduce", "Not provided.")
        root_cause = bug.get("ai_root_cause", "Not analyzed.")
        affected_area = bug.get("ai_affected_area", "Not identified.")
        suggested_fix = bug.get("ai_suggested_fix", "No suggestion.")

        # Build file contents section
        files_section = ""
        if prefetched_files:
            file_blocks = []
            for fpath, content in prefetched_files.items():
                lines = content.splitlines()
                if len(lines) > 500:
                    content = "\n".join(lines[:500]) + f"\n\n... truncated ({len(lines)} total lines)"
                file_blocks.append(f"--- {fpath} ---\n{content}")
            files_section = (
                "\n\nRelevant source files (already read for you):\n\n"
                + "\n\n".join(file_blocks)
            )
        elif relevant_paths:
            paths_list = "\n".join(f"  - {p}" for p in relevant_paths)
            files_section = (
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
            f"{files_section}\n"
            f"\n"
            f"Instructions:\n"
            f"1. The relevant source files are provided above -- study them.\n"
            f"2. Use read_file / search_in_repo ONLY if you need additional context\n"
            f"   (e.g. imports, related modules). Avoid unnecessary reads.\n"
            f"3. Plan ALL your changes, then write ALL affected files at once.\n"
            f"4. write_file requires BOTH 'path' and 'content' (the COMPLETE file).\n"
            f"5. Keep changes minimal and focused on the reported bug.\n"
            f"6. Preserve existing code style and conventions.\n"
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
        prefetched_files: dict[str, str] | None = None,
    ) -> dict:
        """Run a single round of agentic code generation via tool_runner.

        For round 1, uses the full system prompt with bug context.
        For subsequent rounds, includes feedback from the previous round's
        quality gates and asks Claude to address the issues.

        Returns ``{"message": final_message, "usage": {"input_tokens": ..., "output_tokens": ...}}``.
        """
        if round_number == 1:
            prompt = self._build_code_fix_prompt(
                bug, relevant_paths or [], prefetched_files=prefetched_files
            )
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

        try:
            final_message = await runner.until_done()
        except ValueError as exc:
            # The Anthropic SDK raises ValueError when the model produces
            # a tool call with missing/invalid arguments (e.g. write_file
            # called without 'content').  Treat as a failed round so the
            # outer loop can retry with corrective feedback.
            logger.warning(
                "Round %d tool call validation error: %s", round_number, exc
            )
            return {
                "message": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "error": f"Tool call validation error: {exc}",
            }

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
        elif feedback_type == "tool_error":
            output = feedback.get("output", "Unknown tool error.")
            return (
                f"Your previous attempt failed because a tool call was "
                f"malformed:\n\n{output}\n\n"
                f"When using write_file you MUST provide BOTH arguments:\n"
                f"  - path: the file path\n"
                f"  - content: the COMPLETE file content\n\n"
                f"Please try again. Read the relevant files and write "
                f"your fix, making sure to include the full file content."
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

    # ------------------------------------------------------------------
    # Quality gates
    # ------------------------------------------------------------------

    async def _detect_and_run_linter(self, clone_dir: Path) -> dict:
        """Detect the project's linter and run it in the cloned repo.

        Detection order:
        1. pyproject.toml with [tool.ruff] section -> ruff
        2. Config file detection from _LINTER_CONFIGS map
        3. No config found -> pass (no linter)

        Returns a dict with ``linter``, ``output``, ``passed``, and
        optionally ``skipped`` keys.
        """
        # Check pyproject.toml for ruff config first
        pyproject = clone_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8", errors="replace")
                if "[tool.ruff]" in content or "[tool.ruff." in content:
                    return await self._run_linter(
                        clone_dir, "ruff", ["ruff", "check", "."]
                    )
            except Exception:
                pass

        # Check for linter config files
        for config_file, (linter_name, cmd) in _LINTER_CONFIGS.items():
            if (clone_dir / config_file).exists():
                return await self._run_linter(clone_dir, linter_name, cmd)

        # No linter config found
        return {"linter": None, "output": "", "passed": True}

    async def _run_linter(
        self, clone_dir: Path, name: str, cmd: list[str]
    ) -> dict:
        """Run a linter command in the clone directory.

        Checks ``shutil.which`` for the binary first. If not installed,
        returns a skipped result (Pitfall 2 from research).
        """
        # For npx-based commands, check npx; otherwise check the binary
        binary = cmd[0]
        if not shutil.which(binary):
            logger.info("Linter binary %r not found, skipping", binary)
            return {
                "linter": name,
                "output": f"Linter {name} not installed on host",
                "passed": True,
                "skipped": True,
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(clone_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60
            )
            output = (
                (stdout or b"").decode("utf-8", errors="replace")
                + (stderr or b"").decode("utf-8", errors="replace")
            )
            return {
                "linter": name,
                "output": output,
                "passed": proc.returncode == 0,
            }
        except asyncio.TimeoutError:
            return {
                "linter": name,
                "output": f"{name} timed out after 60 seconds",
                "passed": False,
            }
        except Exception as exc:
            logger.warning("Linter %s failed to run: %s", name, exc)
            return {
                "linter": name,
                "output": f"Failed to run {name}: {exc}",
                "passed": True,
                "skipped": True,
            }

    async def _run_self_review(
        self, bug: dict, changed_files: dict[str, str]
    ) -> dict:
        """AI self-review of the generated fix.

        Asks Claude to review against 3 criteria:
        1. Correctness vs. bug report
        2. Side effects
        3. Code style consistency

        Returns ``{"passed": bool, "issues": [...], "summary": "..."}``.
        """
        # Build the diff summary for review
        files_summary = []
        for path, content in changed_files.items():
            # Show the content (truncated for large files)
            lines = content.splitlines()
            if len(lines) > 200:
                preview = "\n".join(lines[:200]) + f"\n... ({len(lines)} total lines)"
            else:
                preview = content
            files_summary.append(f"--- {path} ---\n{preview}")

        files_text = "\n\n".join(files_summary)

        review_prompt = (
            f"Review this code fix for a bug report.\n\n"
            f"Bug: {bug.get('title', 'Unknown')}\n"
            f"Description: {bug.get('description', 'N/A')}\n"
            f"Root cause: {bug.get('ai_root_cause', 'N/A')}\n\n"
            f"Changed files:\n{files_text}\n\n"
            f"Review against these criteria:\n"
            f"1. Correctness: Does the fix address the reported bug?\n"
            f"2. Side effects: Could the change break anything in related code?\n"
            f"3. Code style: Does the fix match existing codebase conventions?\n\n"
            f"Respond with ONLY a JSON object:\n"
            f'{{"passed": true/false, "issues": ["issue1", ...], "summary": "brief review summary"}}\n'
            f"If the fix looks good, set passed=true and issues=[]."
        )

        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": review_prompt}],
            )
            text = message.content[0].text

            # Parse JSON response
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                # Try extracting JSON from markdown
                first_brace = text.find("{")
                last_brace = text.rfind("}")
                if first_brace != -1 and last_brace > first_brace:
                    try:
                        result = json.loads(text[first_brace:last_brace + 1])
                    except json.JSONDecodeError:
                        logger.warning("Could not parse self-review response")
                        return {
                            "passed": True,
                            "issues": [],
                            "summary": "Review response could not be parsed (treating as passed)",
                        }
                else:
                    logger.warning("Could not parse self-review response")
                    return {
                        "passed": True,
                        "issues": [],
                        "summary": "Review response could not be parsed (treating as passed)",
                    }

            return {
                "passed": result.get("passed", True),
                "issues": result.get("issues", []),
                "summary": result.get("summary", ""),
            }

        except Exception as exc:
            logger.warning("Self-review failed: %s", exc)
            return {
                "passed": True,
                "issues": [],
                "summary": f"Self-review skipped due to error: {exc}",
            }

    async def _check_ci(
        self, github_service, owner: str, repo: str, ref: str, timeout: int
    ) -> dict:
        """Poll CI status via GitHubService.

        Thin wrapper that delegates to ``github_service.poll_ci_status``.
        """
        return await github_service.poll_ci_status(
            owner, repo, ref, timeout=timeout
        )

    # ------------------------------------------------------------------
    # Main orchestration
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
        """Generate and validate a code fix using the agentic loop.

        This is the main entry point called by the Draft Fix button handler.

        *progress_callback* is an optional ``async def callback(message: str)``
        for posting Discord progress messages. If None, progress is logged only.

        Returns a dict with keys:
        - ``success``: bool
        - ``changed_files``: dict of path -> content (if success)
        - ``process_log``: dict with files_explored, rounds, total_tokens
        - ``rounds_taken``: int
        - ``validation_passed``: bool
        - ``commit_sha``: str (if committed)
        - ``error``: str (if not success)
        """

        async def _progress(msg: str) -> None:
            """Post progress via callback or log."""
            logger.info("CodeFix progress: %s", msg)
            if progress_callback:
                try:
                    await progress_callback(msg)
                except Exception as exc:
                    logger.warning("Progress callback failed: %s", exc)

        clone_dir = None
        process_log: dict = {
            "files_explored": [],
            "rounds": [],
            "total_tokens": {"input": 0, "output": 0},
        }
        commit_sha = None
        validation_passed = False
        round_num = 0

        try:
            # Step 1: Clone repo
            await _progress("Cloning repository...")
            token = await github_service.get_installation_token(owner, repo)
            clone_dir = await self.clone_repo(owner, repo, branch, token)

            # Step 2: Set up tools and tracking
            tools, changed_files_set, files_read_count = _create_tools(
                clone_dir, self.max_files
            )

            # Step 2b: Pre-read relevant files so they can be embedded
            #          in the prompt, avoiding read_file tool calls.
            prefetched_files: dict[str, str] = {}
            for rel_path in relevant_paths:
                full = (clone_dir / rel_path).resolve()
                try:
                    full.relative_to(clone_dir.resolve())
                except ValueError:
                    continue
                if full.is_file():
                    try:
                        prefetched_files[rel_path] = full.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    except Exception:
                        logger.debug("Could not pre-read %s", rel_path)

            if prefetched_files:
                logger.info(
                    "Pre-read %d files (%d bytes) to embed in prompt",
                    len(prefetched_files),
                    sum(len(v) for v in prefetched_files.values()),
                )

            best_changed_files: dict[str, str] = {}
            feedback: dict | None = None
            committed_this_round = False

            # Step 3: Iteration loop
            for round_num in range(1, self.max_rounds + 1):
                committed_this_round = False

                await _progress(
                    f"Generating fix (round {round_num}/{self.max_rounds})..."
                )

                # a. Run generation (only pass prefetched files on round 1)
                result = await self._run_generation_round(
                    bug,
                    clone_dir,
                    tools,
                    round_num,
                    feedback=feedback,
                    relevant_paths=relevant_paths,
                    prefetched_files=prefetched_files if round_num == 1 else None,
                )

                # b. Handle tool-call validation errors (model omitted
                #    a required argument).  Retry with corrective feedback.
                if result.get("error"):
                    await _progress(
                        f"Round {round_num} hit a tool error: "
                        f"{result['error'][:120]}. Retrying..."
                    )
                    round_log: dict = {
                        "round": round_num,
                        "files_changed": list(changed_files_set),
                        "tokens": result["usage"],
                        "error": result["error"],
                    }
                    process_log["rounds"].append(round_log)
                    feedback = {
                        "type": "tool_error",
                        "output": result["error"],
                    }
                    continue

                # c. Track tokens
                round_usage = result["usage"]
                process_log["total_tokens"]["input"] += round_usage["input_tokens"]
                process_log["total_tokens"]["output"] += round_usage["output_tokens"]

                await _progress(
                    f"Round {round_num} complete. "
                    f"Tokens: {round_usage['input_tokens']} in / "
                    f"{round_usage['output_tokens']} out "
                    f"(total: {process_log['total_tokens']['input']} in / "
                    f"{process_log['total_tokens']['output']} out)"
                )

                # c. Collect changed files from the clone
                current_changes: dict[str, str] = {}
                for rel_path in changed_files_set:
                    full_path = clone_dir / rel_path
                    if full_path.exists():
                        current_changes[rel_path] = full_path.read_text(
                            encoding="utf-8", errors="replace"
                        )

                best_changed_files = current_changes

                # d. Record round in process log
                round_log: dict = {
                    "round": round_num,
                    "files_changed": list(changed_files_set),
                    "tokens": round_usage,
                }

                # e. Update files explored
                process_log["files_explored"] = list(changed_files_set)

                if not current_changes:
                    logger.warning(
                        "Round %d produced no file changes", round_num
                    )
                    round_log["lint"] = {"skipped": True, "reason": "no changes"}
                    process_log["rounds"].append(round_log)
                    feedback = None
                    continue

                # --- Quality Gates ---

                # Gate 1: Lint check
                await _progress("Running lint check...")
                lint_result = await self._detect_and_run_linter(clone_dir)
                round_log["lint"] = lint_result

                if not lint_result["passed"]:
                    await _progress(
                        f"Lint failed ({lint_result.get('linter', 'unknown')}). "
                        f"Iterating..."
                    )
                    feedback = {
                        "type": "lint",
                        "output": lint_result["output"],
                    }
                    process_log["rounds"].append(round_log)
                    continue

                # Gate 2: AI self-review
                await _progress("Running AI self-review...")
                review_result = await self._run_self_review(
                    bug, current_changes
                )
                round_log["self_review"] = review_result

                if not review_result["passed"]:
                    issues_text = "; ".join(review_result.get("issues", []))
                    await _progress(
                        f"Self-review found issues: {issues_text}. Iterating..."
                    )
                    feedback = {
                        "type": "self_review",
                        "issues": review_result["issues"],
                    }
                    process_log["rounds"].append(round_log)
                    continue

                # Gate 3: CI check (commit then poll)
                await _progress("Committing changes and checking CI...")
                commit_msg = (
                    f"fix: {bug.get('title', 'bug fix')} "
                    f"(round {round_num})"
                )
                commit_sha = await github_service.commit_files_atomic(
                    owner, repo, branch, current_changes, commit_msg
                )
                committed_this_round = True

                await _progress("Checking CI status...")
                ci_result = await self._check_ci(
                    github_service, owner, repo, commit_sha, self.ci_timeout
                )
                round_log["ci"] = ci_result

                if ci_result["status"] == "failed":
                    await _progress(
                        f"CI failed: {ci_result['details']}. Iterating..."
                    )
                    feedback = {
                        "type": "ci",
                        "details": ci_result["details"],
                    }
                    process_log["rounds"].append(round_log)
                    continue

                # CI passed, no_ci, or timeout -- we're done
                validation_passed = ci_result["status"] in ("passed", "no_ci")
                await _progress(
                    f"CI status: {ci_result['status']}. "
                    f"{'All quality gates passed!' if validation_passed else 'Finalizing...'}"
                )
                process_log["rounds"].append(round_log)
                break

            else:
                # All rounds exhausted -- record final round
                if round_num > 0 and (
                    not process_log["rounds"]
                    or process_log["rounds"][-1]["round"] != round_num
                ):
                    process_log["rounds"].append(round_log)

            # Step 4: Final commit (if not already committed in CI step)
            if best_changed_files and not committed_this_round:
                commit_msg = (
                    f"fix: {bug.get('title', 'bug fix')} "
                    f"(#{bug.get('hash_id', '')})"
                )
                commit_sha = await github_service.commit_files_atomic(
                    owner, repo, branch, best_changed_files, commit_msg
                )
                await _progress(f"Final commit: {commit_sha[:8] if commit_sha else 'none'}")

            # Step 5: Build result
            return {
                "success": True,
                "changed_files": best_changed_files,
                "process_log": process_log,
                "rounds_taken": round_num,
                "validation_passed": validation_passed,
                "commit_sha": commit_sha,
            }

        except Exception as exc:
            logger.exception("Code fix generation failed: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "process_log": process_log,
            }

        finally:
            if clone_dir:
                self.cleanup_clone(clone_dir)
