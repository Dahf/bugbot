# Phase 5: AI Code Fix -- Agentic Multi-Step Code Generation in Draft Fix Flow - Research

**Researched:** 2026-02-24
**Domain:** Agentic AI code generation, GitHub API (Git Data + Checks), subprocess linting, async temp directory management
**Confidence:** HIGH

## Summary

Phase 5 upgrades the existing Draft Fix button from a scaffolding tool (creates branch + PR with `.bugbot/context.md`) to an agentic AI code generation pipeline. The existing infrastructure from Phase 3 (branch creation, PR opening, context commits) is reused; this phase replaces the "delegate to external tools" approach with a multi-step loop where Claude reads source code, generates fix code, validates through lint/self-review/CI, and iterates up to 3 rounds.

The Anthropic Python SDK (v0.83.0, already installed) provides a `beta_async_tool` decorator and `tool_runner` API that handles the agentic loop automatically -- Claude requests tools, the runner executes them and feeds results back, looping until Claude returns a final answer. The project already uses `AsyncAnthropic` for bug analysis; the code fix service will use the same client with tool definitions for `read_file`, `write_file`, `search_files`, and `run_lint`. githubkit (v0.14.4, already installed) provides all required Git Data APIs (`async_create_blob`, `async_create_tree`, `async_create_commit`, `async_update_ref`) for atomic multi-file commits, and Checks APIs (`async_list_for_ref`) for CI status polling.

**Primary recommendation:** Build a new `CodeFixService` class that orchestrates a 3-round agentic loop using the Anthropic `tool_runner` API with custom async tools for file exploration and code generation, then commits all changes atomically via the GitHub Git Data API (blobs + trees + commits), and polls CI status via the GitHub Checks API.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Multi-step agentic loop: Claude generates a fix, validates it, and iterates if issues are found
- Loop triggers (all three, in sequence per round): lint/syntax checks, AI self-review, test results from CI
- Maximum 3 iteration rounds before finalizing
- If all rounds exhausted without a clean fix: submit the best attempt anyway, with a note in the PR body that validation didn't fully pass
- Interactive exploration: Claude can request additional files during the loop (follow imports, read related modules)
- Repo access via local clone (clone into temp directory for fast file reads and grep/search)
- Cap at 15 files read total across all exploration
- Run the project's actual linter (detect and use whatever linter config the repo has -- ruff, eslint, etc.)
- Feed lint errors back to Claude for the next iteration round
- Claude reviews its own fix for three criteria: correctness vs. bug report, side effects, code style consistency
- Push the fix to the feature branch and check for GitHub Actions CI pipeline
- If CI exists: wait for CI results, feed failures back to Claude for the next round
- If no CI pipeline detected: skip the test validation step entirely
- Only the final version is committed to the branch (squash all iterations into one clean commit)
- PR body includes a collapsible process log section (files explored, rounds taken, what changed per round, validation results)
- Live progress messages posted in the bug's Discord thread as each step happens
- Fire-and-forget: no cancel button during generation
- Completion notification as a rich embed: files changed, rounds taken, validation results, PR link, diff summary
- Token usage / cost tracking visible in progress messages (per-round counts and running total)

### Claude's Discretion
- Whether to provide the full file tree upfront vs. discover as needed
- Exact progress message wording and timing
- How to detect and invoke the project's linter
- Temp directory management for local clones
- How to structure the collapsible process log in the PR body

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic (AsyncAnthropic) | >=0.80.0 (installed: 0.83.0) | Agentic AI code generation with tool use | Already in project; `beta_async_tool` and `tool_runner` provide built-in agentic loop management |
| githubkit | >=0.14.0 (installed: 0.14.4) | Git Data API (blobs, trees, commits) + Checks API (CI status) | Already in project; provides typed async methods for all required GitHub REST endpoints |
| asyncio.subprocess | stdlib | Run linters asynchronously in the cloned repo | Standard library; non-blocking subprocess execution in async context |
| tempfile | stdlib | Manage temporary clone directories | Standard library; `TemporaryDirectory` with cleanup |
| shutil | stdlib | Remove clone directories on cleanup | Standard library fallback for Windows path issues |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiohttp | >=3.9.0 (installed) | HTTP requests if needed for tarball downloads | Alternative to git clone for smaller repos |
| discord.py | >=2.6.0 (installed) | Progress messages in Discord threads | Already in project; used for live progress updates |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Local git clone | GitHub Contents API (already used) | Clone enables grep/search and linter execution; API-only cannot run linters locally |
| Manual agentic loop | Anthropic `tool_runner` (beta) | Tool runner handles message accumulation, error handling, and loop management automatically; reduces boilerplate significantly |
| Manual tool use loop | Claude Agent SDK | Agent SDK is heavier; tool_runner on the existing AsyncAnthropic client is lighter and already available |
| One-file-at-a-time commits | Git Data API (blob+tree+commit) | Git Data API commits all files atomically in a single commit -- required by the "squash all iterations" decision |

## Architecture Patterns

### Recommended Project Structure
```
src/
  services/
    ai_analysis.py          # Existing -- bug analysis service
    github_service.py       # Existing -- extend with Git Data + Checks methods
    code_fix_service.py     # NEW -- agentic code fix orchestrator
  views/
    bug_buttons.py          # Existing -- modify _handle_draft_fix to call CodeFixService
  utils/
    github_templates.py     # Existing -- extend with process log builder
```

### Pattern 1: Agentic Loop with Anthropic tool_runner
**What:** Use the Anthropic SDK's `beta_async_tool` decorator to define tools Claude can call, and `tool_runner` to manage the loop automatically.
**When to use:** For the core code generation loop where Claude reads files, generates fixes, and iterates.
**Example:**
```python
# Source: Anthropic official docs (platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use)
from anthropic import AsyncAnthropic, beta_async_tool

@beta_async_tool
async def read_file(path: str) -> str:
    """Read a file from the cloned repository.

    Args:
        path: Relative file path in the repository
    """
    # Read from local clone
    full_path = clone_dir / path
    return full_path.read_text()

@beta_async_tool
async def write_file(path: str, content: str) -> str:
    """Write or modify a file in the working copy.

    Args:
        path: Relative file path from repo root
        content: The complete file content to write
    """
    full_path = clone_dir / path
    full_path.write_text(content)
    return f"Written {len(content)} bytes to {path}"

client = AsyncAnthropic(api_key=api_key)
runner = client.beta.messages.tool_runner(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,
    tools=[read_file, write_file, search_files, list_directory],
    messages=[{"role": "user", "content": system_context + bug_context}],
)
final_message = await runner.until_done()
```

### Pattern 2: Atomic Multi-File Commit via Git Data API
**What:** Commit multiple file changes in a single atomic commit using GitHub's low-level Git Data API (blobs, trees, commits, refs).
**When to use:** When committing the final fix to the feature branch -- ensures all changes appear in one clean commit.
**Example:**
```python
# Source: GitHub REST API docs (docs.github.com/en/rest/git/trees)
# Step 1: Create blobs for each changed file
blob_shas = {}
for path, content in changed_files.items():
    resp = await gh.rest.git.async_create_blob(
        owner, repo, content=content, encoding="utf-8"
    )
    blob_shas[path] = resp.parsed_data.sha

# Step 2: Get current tree SHA
ref_resp = await gh.rest.git.async_get_ref(owner, repo, f"heads/{branch}")
current_sha = ref_resp.parsed_data.object_.sha
commit_resp = await gh.rest.git.async_get_commit(owner, repo, current_sha)
base_tree_sha = commit_resp.parsed_data.tree.sha

# Step 3: Create new tree with file changes
tree_items = [
    {"path": p, "mode": "100644", "type": "blob", "sha": s}
    for p, s in blob_shas.items()
]
tree_resp = await gh.rest.git.async_create_tree(
    owner, repo, tree=tree_items, base_tree=base_tree_sha
)

# Step 4: Create commit
new_commit = await gh.rest.git.async_create_commit(
    owner, repo,
    tree=tree_resp.parsed_data.sha,
    message="fix: bug description",
    parents=[current_sha],
)

# Step 5: Update branch ref
await gh.rest.git.async_update_ref(
    owner, repo, f"heads/{branch}", sha=new_commit.parsed_data.sha
)
```

### Pattern 3: CI Status Polling via Checks API
**What:** Poll GitHub's Checks API to determine if CI has completed and whether it passed or failed.
**When to use:** After pushing a fix to the branch, wait for CI results before deciding whether to iterate.
**Example:**
```python
# Source: GitHub REST API docs (docs.github.com/en/rest/checks/runs)
import asyncio

async def wait_for_ci(gh, owner, repo, ref, timeout=300, poll_interval=15):
    """Poll check runs until all complete or timeout."""
    elapsed = 0
    while elapsed < timeout:
        resp = await gh.rest.checks.async_list_for_ref(owner, repo, ref)
        check_runs = resp.parsed_data.check_runs

        if not check_runs:
            return {"status": "no_ci", "details": "No CI pipeline detected"}

        all_complete = all(cr.status == "completed" for cr in check_runs)
        if all_complete:
            failures = [cr for cr in check_runs if cr.conclusion != "success"]
            if failures:
                details = "\n".join(
                    f"- {cr.name}: {cr.conclusion}" for cr in failures
                )
                return {"status": "failed", "details": details}
            return {"status": "passed", "details": "All checks passed"}

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return {"status": "timeout", "details": f"CI did not complete within {timeout}s"}
```

### Pattern 4: Linter Detection and Execution
**What:** Detect which linter a project uses by checking for config files, then run it via `asyncio.subprocess`.
**When to use:** As the first validation step in each iteration round.
**Example:**
```python
# Linter detection heuristic
import asyncio
from pathlib import Path

LINTER_CONFIGS = {
    # Python linters
    "ruff.toml": ("ruff", ["ruff", "check", "."]),
    ".flake8": ("flake8", ["flake8", "."]),
    ".pylintrc": ("pylint", ["pylint", "."]),
    # JS/TS linters
    ".eslintrc.js": ("eslint", ["npx", "eslint", "."]),
    ".eslintrc.json": ("eslint", ["npx", "eslint", "."]),
    ".eslintrc.yml": ("eslint", ["npx", "eslint", "."]),
    "eslint.config.js": ("eslint", ["npx", "eslint", "."]),
    "eslint.config.mjs": ("eslint", ["npx", "eslint", "."]),
    # Rust
    "Cargo.toml": ("cargo", ["cargo", "clippy", "--", "-D", "warnings"]),
    # Go
    "go.mod": ("go", ["go", "vet", "./..."]),
}

async def detect_and_run_linter(clone_dir: Path) -> dict:
    """Detect project linter and run it. Returns lint results."""
    # Check pyproject.toml for ruff config
    pyproject = clone_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if "[tool.ruff]" in content or "[tool.ruff." in content:
            return await _run_linter(clone_dir, "ruff", ["ruff", "check", "."])

    for config_file, linter_info in LINTER_CONFIGS.items():
        if (clone_dir / config_file).exists() and linter_info:
            name, cmd = linter_info
            return await _run_linter(clone_dir, name, cmd)

    return {"linter": None, "output": "", "passed": True}

async def _run_linter(clone_dir: Path, name: str, cmd: list[str]) -> dict:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(clone_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    output = (stdout or b"").decode() + (stderr or b"").decode()
    return {"linter": name, "output": output, "passed": proc.returncode == 0}
```

### Pattern 5: Shallow Git Clone into Temp Directory
**What:** Clone the repo shallowly into a temp directory for fast local file access and linter execution.
**When to use:** At the start of the code fix flow, before file exploration begins.
**Example:**
```python
import tempfile
import asyncio
from pathlib import Path

async def clone_repo(owner: str, repo: str, branch: str, token: str) -> Path:
    """Shallow-clone a repo into a temp directory. Returns clone path."""
    clone_dir = Path(tempfile.mkdtemp(prefix=f"bugbot-{owner}-{repo}-"))
    clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"

    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", "--branch", branch,
        clone_url, str(clone_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {stderr.decode()}")

    return clone_dir
```

### Anti-Patterns to Avoid
- **Running linters in the main event loop thread:** Always use `asyncio.subprocess` for linter execution. Blocking the event loop will freeze the Discord bot for all users.
- **Committing after each iteration round:** User decision locks this -- only the final version gets committed. Stage changes locally during rounds, commit once at the end.
- **Reading all files upfront:** Cap at 15 files total. Let Claude request files as needed via the `read_file` tool.
- **Ignoring clone cleanup:** Always clean up temp directories. Use `try/finally` or context manager to ensure cleanup even on errors.
- **Using the Contents API for multi-file commits:** The Contents API (`create_or_update_file_contents`) creates one commit per file. Use the Git Data API (blobs + trees + commits) for atomic multi-file commits.
- **Polling CI without timeout:** Always set a maximum wait time for CI. 5 minutes is reasonable for most workflows.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agentic tool loop | Manual message accumulation + tool dispatch | Anthropic `tool_runner` API (`client.beta.messages.tool_runner`) | Handles message history, tool execution, error recovery, and loop termination automatically |
| Multi-file atomic commit | Multiple `create_or_update_file_contents` calls | GitHub Git Data API (blobs + trees + commits + update ref) | Creates a single atomic commit with all file changes; avoids N commits for N files |
| Token counting | Manual string estimation | `anthropic.AsyncAnthropic.messages.count_tokens()` | Accurate token counting for budget tracking; already available in SDK |
| JSON schema from function | Manually writing tool schemas | `@beta_async_tool` decorator | Automatically generates JSON schema from Python type hints and docstrings |

**Key insight:** The Anthropic SDK's tool_runner and @beta_async_tool decorator eliminate 80% of the agentic loop boilerplate. The manual approach (accumulating messages, checking stop_reason, dispatching tools, feeding results back) is error-prone and verbose. The tool_runner does all of this automatically.

## Common Pitfalls

### Pitfall 1: Clone Auth Token Expiry
**What goes wrong:** GitHub App installation tokens expire after 1 hour. Long-running code fix sessions may fail mid-clone or mid-push.
**Why it happens:** Installation tokens are requested at the start and not refreshed.
**How to avoid:** Get a fresh installation token immediately before any git operation (clone, push). githubkit's `with_auth(as_installation())` handles token rotation for API calls, but git CLI operations need explicit token management.
**Warning signs:** 401 errors from git push after a successful clone.

### Pitfall 2: Linter Not Installed in Clone Environment
**What goes wrong:** The bot detects a ruff/eslint config but the linter binary isn't installed in the bot's execution environment.
**Why it happens:** The linter config describes the project's preference, but the bot's host machine may not have that linter installed.
**How to avoid:** Check if the linter binary exists (via `shutil.which()`) before attempting to run it. If not available, skip the lint step and note it in the process log. Consider pre-installing common linters (ruff, eslint) in the bot's deployment environment.
**Warning signs:** `FileNotFoundError` or command-not-found errors during subprocess execution.

### Pitfall 3: Windows Path Issues with Temp Directories
**What goes wrong:** `tempfile.TemporaryDirectory` cleanup fails on Windows when git creates read-only files in `.git/`.
**Why it happens:** Git marks some pack files as read-only; Python's `shutil.rmtree` cannot delete them without an error handler.
**How to avoid:** Use `shutil.rmtree(clone_dir, onerror=_handle_readonly)` with a handler that calls `os.chmod` to make files writable before deletion. Or use `tempfile.mkdtemp()` with manual cleanup in a `finally` block.
**Warning signs:** `PermissionError` during cleanup on Windows; temp directories accumulating over time.

### Pitfall 4: Context Window Overflow
**What goes wrong:** After reading many large files and accumulating multiple rounds of messages, the context window exceeds Claude's limit.
**Why it happens:** Each file read, each lint output, and each iteration round adds to the conversation history.
**How to avoid:** Limit individual file reads to a reasonable size (200 lines or 50KB, matching existing Phase 3 limits). Cap total files at 15 (locked decision). Use `count_tokens()` before each API call to track usage. Consider summarizing earlier rounds if approaching limits.
**Warning signs:** `400 Bad Request` with "context length exceeded" error from the Anthropic API.

### Pitfall 5: CI Polling Race Condition
**What goes wrong:** Check runs haven't been created yet when the bot starts polling, so the API returns 0 check runs, and the bot concludes "no CI pipeline."
**Why it happens:** GitHub Actions takes a few seconds to register check runs after a push event.
**How to avoid:** Wait 10-15 seconds after pushing before the first poll. If the first poll returns 0 check runs, wait and retry once more before concluding no CI exists.
**Warning signs:** CI exists but the bot consistently reports "no CI pipeline detected" -- check for premature first-poll timing.

### Pitfall 6: Agentic Loop Runaway
**What goes wrong:** Claude enters a loop where each iteration generates slightly different but never-passing code, consuming tokens without progress.
**Why it happens:** The 3-round limit prevents infinite loops, but each round can be expensive if Claude reads many files and generates long outputs.
**How to avoid:** Set aggressive `max_tokens` per API call (4096 for code gen). Track token usage per round and abort if a single round exceeds a budget threshold. The 3-round hard cap (locked decision) is the primary safeguard.
**Warning signs:** Rapidly increasing token counts without validation improvements.

## Code Examples

### Complete Agentic Tool Definition Pattern
```python
# Source: Anthropic official docs + project patterns
from anthropic import AsyncAnthropic, beta_async_tool
from pathlib import Path

# Tools are defined as decorated async functions.
# The decorator extracts name, description, and input_schema from
# the function signature and docstring automatically.

files_read_count = 0
MAX_FILES = 15

@beta_async_tool
async def read_file(path: str) -> str:
    """Read a source file from the repository.

    Args:
        path: Relative file path from repo root (e.g., 'src/main.py')
    """
    nonlocal files_read_count
    if files_read_count >= MAX_FILES:
        return "ERROR: File read limit (15) reached. Work with files already read."
    full_path = clone_dir / path
    if not full_path.exists():
        return f"ERROR: File not found: {path}"
    content = full_path.read_text(encoding="utf-8", errors="replace")
    files_read_count += 1
    # Truncate large files
    lines = content.splitlines()
    if len(lines) > 500:
        content = "\n".join(lines[:500]) + f"\n\n... truncated ({len(lines)} total lines)"
    return content

@beta_async_tool
async def write_file(path: str, content: str) -> str:
    """Write a fix to a file. This stages the change for the final commit.

    Args:
        path: Relative file path from repo root
        content: Complete file content (not a diff -- write the full file)
    """
    full_path = clone_dir / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {path}"

@beta_async_tool
async def search_in_repo(query: str, file_pattern: str = "*.py") -> str:
    """Search for a string across repository files using grep.

    Args:
        query: Text to search for (case-insensitive)
        file_pattern: Glob pattern for files to search (default: *.py)
    """
    proc = await asyncio.create_subprocess_exec(
        "grep", "-rn", "-i", "--include", file_pattern, query, str(clone_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    output = stdout.decode()[:5000]  # Cap output size
    if not output:
        return "No matches found."
    return output

@beta_async_tool
async def list_directory(path: str = ".") -> str:
    """List files and directories at the given path.

    Args:
        path: Relative directory path from repo root (default: root)
    """
    target = clone_dir / path
    if not target.is_dir():
        return f"ERROR: Not a directory: {path}"
    entries = sorted(target.iterdir())
    result = []
    for entry in entries[:100]:  # Cap listing
        rel = entry.relative_to(clone_dir)
        prefix = "d " if entry.is_dir() else "f "
        result.append(prefix + str(rel))
    return "\n".join(result)
```

### GitHub Git Data API -- Atomic Multi-File Commit
```python
# Source: GitHub REST API docs (docs.github.com/en/rest/git/trees)
# Verified: githubkit v0.14.4 provides async_create_blob, async_create_tree,
# async_create_commit, async_update_ref

async def commit_fix_files(
    gh, owner: str, repo: str, branch: str,
    changed_files: dict[str, str],  # path -> content
    commit_message: str,
) -> str:
    """Commit multiple file changes as a single atomic commit. Returns commit SHA."""
    # 1. Create blobs
    tree_items = []
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

    # 2. Get current branch HEAD
    ref_resp = await gh.rest.git.async_get_ref(owner, repo, f"heads/{branch}")
    head_sha = ref_resp.parsed_data.object_.sha
    commit_resp = await gh.rest.git.async_get_commit(owner, repo, head_sha)
    base_tree_sha = commit_resp.parsed_data.tree.sha

    # 3. Create new tree
    tree_resp = await gh.rest.git.async_create_tree(
        owner, repo, tree=tree_items, base_tree=base_tree_sha
    )

    # 4. Create commit
    new_commit_resp = await gh.rest.git.async_create_commit(
        owner, repo,
        tree=tree_resp.parsed_data.sha,
        message=commit_message,
        parents=[head_sha],
    )

    # 5. Update branch ref
    await gh.rest.git.async_update_ref(
        owner, repo, f"heads/{branch}",
        sha=new_commit_resp.parsed_data.sha,
    )

    return new_commit_resp.parsed_data.sha
```

### GitHub Checks API -- CI Status Polling
```python
# Source: GitHub REST API docs (docs.github.com/en/rest/checks/runs)
# Verified: githubkit v0.14.4 provides async_list_for_ref on checks namespace

async def poll_ci_status(
    gh, owner: str, repo: str, ref: str,
    timeout: int = 300, poll_interval: int = 15,
    initial_delay: int = 15,
) -> dict:
    """Poll CI check runs until complete or timeout.

    Returns dict with 'status' ('passed', 'failed', 'no_ci', 'timeout')
    and 'details' string.
    """
    # Initial delay to allow GitHub Actions to register check runs
    await asyncio.sleep(initial_delay)

    elapsed = 0
    while elapsed < timeout:
        resp = await gh.rest.checks.async_list_for_ref(owner, repo, ref)
        check_runs = resp.parsed_data.check_runs
        total = resp.parsed_data.total_count

        if total == 0:
            # Second chance: no runs yet, wait once more
            if elapsed == 0:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue
            return {"status": "no_ci", "details": "No CI pipeline detected"}

        all_complete = all(cr.status == "completed" for cr in check_runs)
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
            return {"status": "passed", "details": f"All {total} checks passed"}

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return {"status": "timeout", "details": f"CI did not complete within {timeout}s"}
```

### Installation Token for Git Clone Auth
```python
# Source: githubkit docs + GitHub App auth patterns
# The installation token can be retrieved from githubkit for use with git CLI

async def get_installation_token(github_service, owner: str, repo: str) -> str:
    """Get an installation access token for git CLI operations."""
    gh = await github_service.get_installation_client(owner, repo)
    # The installation auth token is available from the auth object
    # githubkit handles token creation internally via as_installation()
    # For git clone, we need the raw token string
    token = await gh.auth.get_access_token(gh)
    return token.token
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual agentic loop (accumulate messages, check stop_reason) | `tool_runner` API with `@beta_async_tool` | Anthropic SDK ~v0.70+ (2025) | Eliminates 80% of agentic loop boilerplate |
| One-commit-per-file via Contents API | Git Data API (blobs + trees + commits) | GitHub API v3 (stable) | Atomic multi-file commits in a single operation |
| Phase 3 context scaffolding (.bugbot/context.md) | Phase 5 real AI code generation | This phase | Replaces scaffolding with actual code fixes |

**Deprecated/outdated:**
- The manual tool use loop pattern (checking `stop_reason == "tool_use"`, building message arrays manually) still works but is verbose compared to `tool_runner`. The `tool_runner` API is in beta but stable and recommended by Anthropic for new implementations.
- The `create_or_update_file_contents` API used in Phase 3 for single-file commits is inadequate for multi-file atomic commits. The Git Data API (used by Phase 5) is the correct approach.

## Open Questions

1. **Installation token extraction for git CLI**
   - What we know: githubkit's `as_installation()` handles token rotation for API calls automatically. For `git clone` via CLI, we need the raw token string.
   - What's unclear: The exact method to extract the raw installation token from githubkit's auth layer. The `get_access_token` method may have a different signature.
   - Recommendation: Test token extraction during implementation. Fallback: use the GitHub Contents API's tarball download endpoint (`repos.download_tarball_archive`) instead of git clone -- it's authenticated through githubkit and avoids the token extraction problem entirely. The tradeoff is losing the ability to run `git diff` for change detection, but `difflib` in Python's stdlib can fill that gap.

2. **Model selection for code generation**
   - What we know: The project currently uses `claude-haiku-4-5-20251001` for bug analysis (fast, cheap). Code generation is more complex and may benefit from a more capable model.
   - What's unclear: The optimal model for code fix generation. Haiku may produce lower-quality fixes; Sonnet/Opus would be more expensive but higher quality.
   - Recommendation: Default to `claude-sonnet-4-5-20250929` (good balance of quality and cost for code generation). Make it configurable via an env var (`ANTHROPIC_CODE_FIX_MODEL`) so the user can upgrade to Opus or downgrade to Haiku as needed.

3. **Linter binary availability**
   - What we know: The bot will detect linter configs in the cloned repo. Running the linter requires the binary to be installed on the bot's host.
   - What's unclear: Whether the deployment environment has ruff, eslint, etc. pre-installed. Installing linters on-demand is possible but slow and adds complexity.
   - Recommendation: Check `shutil.which()` for the detected linter binary. If not found, skip linting and note "linter not available" in the process log. Document recommended linter installations for the bot's deployment environment.

## Sources

### Primary (HIGH confidence)
- Anthropic official docs: [How to implement tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use) -- tool_runner API, @beta_async_tool, parallel tool use, tool result formatting
- GitHub REST API docs: [Check Runs](https://docs.github.com/en/rest/checks/runs) -- list check runs for ref, status/conclusion fields
- GitHub REST API docs: [Git Trees](https://docs.github.com/en/rest/git/trees) -- create tree for multi-file atomic commits
- githubkit source (v0.14.4, verified locally) -- `async_create_blob`, `async_create_tree`, `async_create_commit`, `async_update_ref`, `async_list_for_ref` all confirmed available
- Anthropic Python SDK (v0.83.0, verified locally) -- `beta_async_tool`, `tool_runner`, `count_tokens` all confirmed available

### Secondary (MEDIUM confidence)
- [Multi-file commit via GitHub API](https://dev.to/bro3886/create-a-folder-and-push-multiple-files-under-a-single-commit-through-github-api-23kc) -- step-by-step blob+tree+commit+ref workflow verified against official docs
- [Agentic loop pattern](https://docs.temporal.io/ai-cookbook/agentic-loop-tool-call-claude-python) -- message accumulation and tool dispatch patterns, cross-verified with Anthropic official docs
- Python docs: [tempfile](https://docs.python.org/3/library/tempfile.html) -- TemporaryDirectory, mkdtemp usage patterns
- Python docs: [asyncio.subprocess](https://docs.python.org/3/library/asyncio-subprocess.html) -- async subprocess execution for linter invocation

### Tertiary (LOW confidence)
- Installation token extraction from githubkit auth layer -- needs validation during implementation; the exact API surface for raw token access is unclear from available documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and verified; API surfaces confirmed via local inspection
- Architecture: HIGH -- agentic loop pattern well-documented by Anthropic; Git Data API pattern well-documented by GitHub; both verified against installed library versions
- Pitfalls: HIGH -- identified from direct experience with the codebase (Windows path issues, async subprocess) and documented API behavior (CI polling race conditions, token expiry)

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (stable APIs, no fast-moving changes expected)
