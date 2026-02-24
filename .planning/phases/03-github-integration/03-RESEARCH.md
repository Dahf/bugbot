# Phase 3: GitHub Integration - Research

**Researched:** 2026-02-24
**Domain:** GitHub API integration (Apps, REST API, Webhooks) + Discord bot orchestration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- GitHub App installation for fine-grained permissions (not personal access tokens)
- Discord `/init` slash command walks user through connecting a repo
- `/init` provides the GitHub App install link, then enters a waiting/polling loop until installation is detected
- After install, bot auto-detects which repos the App was installed on and lets user pick if multiple
- Single repo per Discord server (not per-channel)
- Issue body includes ALL context: bug description + steps, device/environment info, AI analysis results, and Discord thread link
- Auto-apply labels from AI analysis (priority labels like P1-critical, area labels like area:auth)
- Bot auto-creates missing labels (with colors) if they don't exist in the repo
- Single configured repo per server (set via /init)
- Hybrid approach: bot creates branch + PR scaffold, external tool (GitHub Copilot/BugBot) handles actual code generation
- If external tool doesn't produce a fix, leave PR as a shell with full bug context (no Claude fallback)
- No file/directory guardrails -- external tool can touch any files it determines are relevant
- Branch naming: `bot/bug-{id}-{short-desc}` (e.g., `bot/bug-42-login-crash`)
- Never commit to default branch (main/master) -- always feature branches
- PR description includes: bug summary, AI analysis, Discord thread link, and `Closes #{issue}` to auto-close on merge
- If branch already exists for a bug (re-trigger), block and notify user with link to existing branch/PR
- Auto-delete branch on PR merge
- When issue is created: update original bug embed (status + issue link) AND post message in bug thread
- When PR is opened: update embed status to 'fix_drafted' AND post PR link in thread
- Full GitHub webhook tracking: listen for PR status changes (merged, closed, review requested) and update Discord
- Auto-resolve on merge: when PR is merged, bug status automatically becomes 'resolved' and embed updates

### Claude's Discretion
- Exact GitHub App permissions scope
- GitHub webhook event filtering (which events to subscribe to)
- Rate limit retry/backoff strategy (GH-09)
- Issue template formatting details
- Label color scheme

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Summary

Phase 3 connects the Discord bug-tracking bot to GitHub, enabling two one-click workflows: "Create Issue" (builds a structured GitHub issue from an analyzed bug report) and "Draft Fix" (creates a branch and PR scaffold for an external code-generation tool). The phase also adds bidirectional linking (Discord embeds update when GitHub events fire) and a `/init` slash command for GitHub App installation.

The recommended library is **githubkit** (v0.14.4) -- a modern, fully-typed, async-native Python SDK that wraps the entire GitHub REST API with auto-generated typed models. It has first-class GitHub App authentication support, built-in retry for rate limits and server errors, webhook signature verification and typed payload parsing, and uses the `async_` method prefix convention that fits naturally with the existing async/aiohttp codebase.

**Primary recommendation:** Use `githubkit[auth-app]>=0.14.0,<1.0.0` for all GitHub API interactions, extend the existing aiohttp webhook server to receive GitHub webhook events alongside the Supabase webhook, and store GitHub App credentials + per-guild repo config in the existing SQLite database.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GH-01 | User can create a GitHub issue from a bug report via button | githubkit `rest.issues.async_create()` with labels, body, title; button handler already scaffolded in `bug_buttons.py` (currently shows "coming soon") |
| GH-02 | GitHub issue includes structured details (description, steps, device info, analysis results) | Issue body built from existing `bug` dict fields; use markdown template with sections |
| GH-03 | GitHub issue links back to the Discord thread | Discord thread URL format: `https://discord.com/channels/{guild_id}/{thread_id}` -- constructed from stored `channel_id`/`thread_id` in bugs table |
| GH-04 | User can trigger AI-drafted code fix via button | Button handler creates branch via `rest.git.async_create_ref()`, creates PR via `rest.pulls.async_create()` with scaffold body |
| GH-05 | AI code fix uses repository context (reads relevant source files) | Hybrid approach: PR scaffold includes bug context; external tool (Copilot/BugBot) reads repo -- bot does NOT read source files directly |
| GH-06 | Bot creates a feature branch, commits the fix, and opens a PR automatically | `POST /repos/{owner}/{repo}/git/refs` to create branch from default branch SHA, then `POST /repos/{owner}/{repo}/pulls` to open PR |
| GH-07 | PR description includes bug context, analysis, and link to Discord thread | Markdown template in PR body with bug summary, AI analysis fields, Discord thread link, and `Closes #{issue}` |
| GH-08 | Bot never commits to the default branch (main/master) | Branch always created from default branch SHA via git refs API; PR always targets default branch as base; no direct commit operations |
| GH-09 | Bot handles GitHub API rate limits with retry and backoff | githubkit built-in `RetryChainDecision(RetryRateLimit(), RetryServerError())` with configurable max retries |
| GH-10 | Bot cleans up merged/stale branches | Two strategies: (1) GitHub repo setting `delete_branch_on_merge=true` via `PATCH /repos`, (2) Webhook-triggered cleanup via `DELETE /repos/{owner}/{repo}/git/refs/{ref}` on PR merge event |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| githubkit[auth-app] | >=0.14.0,<1.0.0 | GitHub REST API client | Async-native, fully typed, auto-generated from GitHub OpenAPI spec, built-in App auth + rate limit retry + webhook parsing. High reputation on Context7 (score 79.9). Latest release 0.14.4 (2026-02-08). |
| PyJWT[crypto] | >=2.4.0,<3.0.0 | JWT for GitHub App auth | Pulled in automatically by githubkit[auth-app] extra; needed for signing App JWTs with RSA private key |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiohttp | (already installed) | Webhook HTTP server | Already runs the Supabase webhook server in `src/cogs/webhook.py`; extend with GitHub webhook route |
| aiosqlite | (already installed) | Database | Already used; extend schema for GitHub App config + per-guild repo mapping |
| discord.py | >=2.6.0 (already installed) | Discord interactions | Already used; add `/init` slash command + enable Create Issue / Draft Fix buttons |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| githubkit | PyGithub | PyGithub is sync-only (would block the event loop); larger community (3207 snippets) but no native async. Would need `asyncio.to_thread()` wrappers everywhere. |
| githubkit | gidgethub | Pure async but lower-level (no typed models, manual JSON handling). Less maintained. |
| githubkit | httpx + raw REST | Maximum control but massive boilerplate for auth, pagination, rate limits, error handling. |

**Installation:**
```bash
pip install "githubkit[auth-app]>=0.14.0,<1.0.0"
```

Add to `requirements.txt`:
```
githubkit[auth-app]>=0.14.0,<1.0.0
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── cogs/
│   ├── webhook.py           # Extended: add GitHub webhook route
│   ├── github_integration.py # NEW: /init command, GitHub webhook event handlers
│   ├── bug_reports.py        # Existing (unchanged)
│   └── ai_analysis.py        # Existing (unchanged)
├── services/
│   ├── ai_analysis.py        # Existing (unchanged)
│   └── github_service.py     # NEW: GitHub API operations (issues, branches, PRs, labels)
├── models/
│   ├── bug.py                # Extended: add github_issue_number, github_pr_number, branch_name columns
│   ├── database.py           # Extended: add github_config table + migration
│   └── github_config.py      # NEW: per-guild GitHub App config CRUD
├── utils/
│   ├── embeds.py             # Extended: add GitHub link fields to summary embed
│   ├── github_templates.py   # NEW: issue body + PR body markdown templates
│   └── webhook_auth.py       # Existing (unchanged)
├── views/
│   └── bug_buttons.py        # Extended: enable Create Issue + Draft Fix buttons
├── config.py                 # Extended: add GitHub App env vars
└── bot.py                    # Extended: init GitHub service in setup_hook
```

### Pattern 1: GitHub App Authentication Flow
**What:** App-level auth (JWT) to discover installations, then installation-level auth (token) for repo operations
**When to use:** Every GitHub API call except listing installations
**Example:**
```python
# Source: Context7 /yanyongyu/githubkit - GitHub App authentication docs
from githubkit import GitHub, AppAuthStrategy
from githubkit.retry import RetryChainDecision, RetryRateLimit, RetryServerError

class GitHubService:
    def __init__(self, app_id: str, private_key: str, client_id: str, client_secret: str):
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
        """Get an installation-authenticated client for a specific repo."""
        resp = await self.app_github.rest.apps.async_get_repo_installation(owner, repo)
        installation = resp.parsed_data
        return self.app_github.with_auth(
            self.app_github.auth.as_installation(installation.id)
        )
```

### Pattern 2: /init Slash Command with Polling Loop
**What:** Discord slash command that guides user through GitHub App installation with a waiting loop
**When to use:** First-time setup of GitHub integration per Discord server
**Example:**
```python
# Conceptual flow for /init command
# 1. Bot sends ephemeral message with GitHub App install link
#    URL: https://github.com/apps/{app-name}/installations/new?state={guild_id}
# 2. Bot enters a polling loop (check every 5s, timeout after 5min)
#    Poll: GET /app/installations via App JWT auth, filter by guild's expected owner
# 3. On detection: list repos for installation, present select menu if multiple
# 4. Store guild_id -> (installation_id, owner, repo) in github_config table
# 5. Confirm setup with embed showing connected repo
```

### Pattern 3: Webhook Event Routing
**What:** Extend existing aiohttp server with a `/webhook/github` endpoint for GitHub events
**When to use:** Receiving GitHub webhook events (PR merged, closed, review requested)
**Example:**
```python
# Source: Context7 /yanyongyu/githubkit - Webhook verification docs
from githubkit.webhooks import verify, parse

async def handle_github_webhook(request):
    raw_body = await request.read()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify(webhook_secret, raw_body, signature):
        return web.json_response({"error": "Invalid signature"}, status=401)

    event_name = request.headers["X-GitHub-Event"]
    event = parse(event_name, raw_body)

    if event_name == "pull_request":
        if event.action == "closed" and event.pull_request.merged:
            # PR merged -> resolve bug, update Discord embed
            await handle_pr_merged(event)
        elif event.action == "closed":
            # PR closed without merge
            await handle_pr_closed(event)
    elif event_name == "installation":
        # New installation detected (backup to polling)
        await handle_installation_created(event)
```

### Pattern 4: Create Issue with Auto-Labels
**What:** Create a GitHub issue with structured body and auto-created labels
**When to use:** "Create Issue" button click
**Example:**
```python
# Source: Context7 /yanyongyu/githubkit - REST API issue creation docs
async def create_issue(self, gh: GitHub, owner: str, repo: str, bug: dict, labels: list[str]):
    # Ensure labels exist (create if missing -- 422 means already exists)
    for label_name, color in self._label_definitions(bug):
        try:
            await gh.rest.issues.async_create_label(owner, repo, name=label_name, color=color)
        except Exception:
            pass  # Label already exists, continue

    # Create the issue
    body = build_issue_body(bug)  # Markdown template with all context
    resp = await gh.rest.issues.async_create(
        owner, repo,
        title=f"[Bug #{bug['hash_id']}] {bug['title']}",
        body=body,
        labels=labels,
    )
    return resp.parsed_data
```

### Pattern 5: Branch + PR Scaffold Creation
**What:** Create a feature branch from default branch, then open a PR with bug context
**When to use:** "Draft Fix" button click
**Example:**
```python
async def create_branch_and_pr(self, gh: GitHub, owner: str, repo: str, bug: dict, issue_number: int):
    # 1. Get default branch SHA
    repo_resp = await gh.rest.repos.async_get(owner, repo)
    default_branch = repo_resp.parsed_data.default_branch
    ref_resp = await gh.rest.git.async_get_ref(owner, repo, f"heads/{default_branch}")
    base_sha = ref_resp.parsed_data.object.sha

    # 2. Create feature branch (never touches default branch -- GH-08)
    branch_name = f"bot/bug-{bug['hash_id']}-{slugify(bug['title'])}"
    await gh.rest.git.async_create_ref(
        owner, repo,
        ref=f"refs/heads/{branch_name}",
        sha=base_sha,
    )

    # 3. Create PR scaffold
    pr_body = build_pr_body(bug, issue_number)  # Includes Closes #{issue}
    pr_resp = await gh.rest.pulls.async_create(
        owner, repo,
        title=f"fix: {bug['title']} (#{bug['hash_id']})",
        head=branch_name,
        base=default_branch,
        body=pr_body,
    )
    return pr_resp.parsed_data
```

### Anti-Patterns to Avoid
- **Storing GitHub PATs per user:** Use GitHub App installation tokens instead. They are auto-rotated, scoped to specific repos, and don't expire when a user leaves the org.
- **Synchronous GitHub calls:** PyGithub is sync-only. Using `asyncio.to_thread()` is a workaround but adds complexity and thread-pool pressure. Use githubkit's native async.
- **Committing files directly to default branch:** Always create a feature branch first. The bot should NEVER have a code path that commits to main/master.
- **Ignoring rate limit headers:** githubkit's auto-retry handles this, but never disable it or add manual sleep() calls on top.
- **Polling without timeout:** The `/init` polling loop MUST have a timeout (recommend 5 minutes) to avoid hanging interactions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GitHub App JWT signing | Custom JWT creation | githubkit `AppAuthStrategy` | JWT requires RS256 signing with private key, token expiry management, and installation token rotation. All handled internally. |
| Rate limit handling | Custom retry/backoff logic | githubkit `RetryChainDecision(RetryRateLimit(), RetryServerError())` | GitHub has primary AND secondary rate limits with different backoff strategies. Built-in handles both. |
| Webhook signature verification | Custom HMAC comparison | githubkit `webhooks.verify()` | Time-constant comparison against X-Hub-Signature-256 header. Don't reimplement crypto. |
| Webhook payload parsing | Manual JSON parsing + field access | githubkit `webhooks.parse()` | Returns fully-typed Pydantic models for every webhook event type. Catches schema changes at import time. |
| GitHub API pagination | Manual link-header following | githubkit built-in pagination | REST API pagination is complex (Link headers, cursor-based for GraphQL). Library handles both. |

**Key insight:** GitHub's API surface is enormous and changes frequently. githubkit auto-generates from GitHub's OpenAPI spec, so API additions/changes are reflected in library updates without manual model maintenance.

## Common Pitfalls

### Pitfall 1: Installation Token Expiry
**What goes wrong:** Installation tokens expire after 1 hour. If you cache a token at startup and reuse it, API calls silently fail after 60 minutes.
**Why it happens:** GitHub App installation tokens are intentionally short-lived for security.
**How to avoid:** githubkit's `AppAuthStrategy.as_installation()` handles token refresh automatically. Never cache raw tokens -- always go through the auth strategy.
**Warning signs:** 401 errors that appear ~1 hour after bot startup.

### Pitfall 2: Discord Interaction Timeout (3-second rule)
**What goes wrong:** GitHub API calls take 1-5 seconds. If Create Issue or Draft Fix triggers multiple sequential API calls before responding to Discord, the interaction times out.
**Why it happens:** Discord requires an initial response within 3 seconds of button click.
**How to avoid:** `defer()` the interaction immediately (already the pattern in the codebase), then perform GitHub operations, then follow up. The existing Analyze button handler demonstrates this pattern perfectly.
**Warning signs:** "This interaction failed" messages in Discord.

### Pitfall 3: Setup URL Spoofing
**What goes wrong:** Malicious users hit the setup URL with fake `installation_id` values to hijack repo connections.
**Why it happens:** GitHub's setup URL includes `installation_id` as a query parameter, but does not guarantee its authenticity.
**How to avoid:** Instead of trusting `installation_id` from the setup URL redirect, use the `/init` polling approach: the bot polls `GET /app/installations` and validates the installation exists before storing it. The `state` parameter (guild_id) provides correlation.
**Warning signs:** Guild configs pointing to repos the server admin doesn't own.

### Pitfall 4: Branch Name Collisions
**What goes wrong:** User clicks "Draft Fix" on a bug that already has a branch/PR, creating a duplicate branch or hitting a 422 error.
**Why it happens:** Re-triggering the Draft Fix button without checking existing state.
**How to avoid:** Before creating a branch, check if `branch_name` column is already set in the bugs table. If yes, respond with a link to the existing PR instead of creating a new one. Also handle 422 from git refs API gracefully (ref already exists).
**Warning signs:** 422 Validation Failed errors from `POST /repos/{owner}/{repo}/git/refs`.

### Pitfall 5: Webhook Secret Confusion
**What goes wrong:** The bot already uses `WEBHOOK_SECRET` for Supabase HMAC validation. If GitHub webhook verification reuses the same env var, changing one breaks the other.
**Why it happens:** Both Supabase and GitHub webhooks use HMAC signatures but with different secrets.
**How to avoid:** Use a SEPARATE secret for GitHub webhooks: `GITHUB_WEBHOOK_SECRET`. The GitHub webhook endpoint must use githubkit's `verify()` with this dedicated secret, not the existing Supabase one.
**Warning signs:** All GitHub webhook deliveries rejected as invalid signature, or Supabase webhooks breaking after GitHub setup.

### Pitfall 6: Missing Labels Return 422
**What goes wrong:** Creating an issue with non-existent label names causes a 422 error.
**Why it happens:** GitHub validates label names at issue creation time.
**How to avoid:** Create labels first (catch 422 "already exists" errors), then create the issue. This is the "ensure labels exist" pattern.
**Warning signs:** Issue creation fails with "Validation Failed" mentioning labels.

## Code Examples

Verified patterns from official sources:

### GitHub App Client Setup
```python
# Source: Context7 /yanyongyu/githubkit - AppAuthStrategy docs
from githubkit import GitHub, AppAuthStrategy
from githubkit.retry import RetryChainDecision, RetryRateLimit, RetryServerError

github_app = GitHub(
    AppAuthStrategy(
        app_id=config.GITHUB_APP_ID,
        private_key=config.GITHUB_PRIVATE_KEY,
        client_id=config.GITHUB_CLIENT_ID,
        client_secret=config.GITHUB_CLIENT_SECRET,
    ),
    auto_retry=RetryChainDecision(
        RetryRateLimit(max_retry=3),
        RetryServerError(max_retry=2),
    ),
)
```

### Get Installation Client for a Repo
```python
# Source: Context7 /yanyongyu/githubkit - async installation auth
resp = await github_app.rest.apps.async_get_repo_installation(owner, repo)
installation = resp.parsed_data
gh = github_app.with_auth(
    github_app.auth.as_installation(installation.id)
)
# gh is now authenticated to act on this specific repo
```

### Create Issue with Labels
```python
# Source: Context7 /yanyongyu/githubkit - REST API issue creation
resp = await gh.rest.issues.async_create(
    owner, repo,
    title=f"[Bug #{bug['hash_id']}] {title}",
    body=issue_body_markdown,
    labels=["P2-high", "area:auth", "bot-created"],
)
issue = resp.parsed_data
# issue.number, issue.html_url available
```

### Create Label (idempotent)
```python
# Source: GitHub REST API docs for labels
try:
    await gh.rest.issues.async_create_label(
        owner, repo, name="P1-critical", color="e11d48", description="Critical priority"
    )
except Exception:
    pass  # 422 means label already exists -- that's fine
```

### Create Branch from Default Branch
```python
# Source: GitHub REST API docs for git refs
# 1. Get default branch SHA
repo_data = (await gh.rest.repos.async_get(owner, repo)).parsed_data
default_branch = repo_data.default_branch
ref_data = (await gh.rest.git.async_get_ref(owner, repo, f"heads/{default_branch}")).parsed_data
base_sha = ref_data.object.sha

# 2. Create branch ref
await gh.rest.git.async_create_ref(
    owner, repo,
    ref=f"refs/heads/bot/bug-{bug_id}-{short_desc}",
    sha=base_sha,
)
```

### Create Pull Request
```python
# Source: Context7 /yanyongyu/githubkit - pull request creation
resp = await gh.rest.pulls.async_create(
    owner, repo,
    title=f"fix: {short_title} (#{bug_id})",
    head=branch_name,
    base=default_branch,
    body=pr_body_markdown,  # includes "Closes #{issue_number}"
)
pr = resp.parsed_data
# pr.number, pr.html_url available
```

### Verify and Parse GitHub Webhook
```python
# Source: Context7 /yanyongyu/githubkit - webhook verification docs
from githubkit.webhooks import verify, parse

async def handle_github_webhook(request):
    raw_body = await request.read()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify(GITHUB_WEBHOOK_SECRET, raw_body, signature):
        return web.json_response({"error": "Invalid signature"}, status=401)

    event_name = request.headers["X-GitHub-Event"]
    event = parse(event_name, raw_body)

    # event is a fully-typed Pydantic model
    if event_name == "pull_request" and event.action == "closed" and event.pull_request.merged:
        # Handle PR merge
        pass
```

### Delete Branch (cleanup)
```python
# Source: GitHub REST API docs for git refs
await gh.rest.git.async_delete_ref(owner, repo, f"heads/{branch_name}")
```

## Discretion Recommendations

### GitHub App Permissions Scope
**Recommendation:** Request the minimum set of repository permissions:

| Permission | Level | Required For |
|------------|-------|--------------|
| Contents | Read & Write | Creating branches (git refs), reading file contents (for PR context) |
| Issues | Read & Write | Creating issues, managing labels |
| Pull Requests | Read & Write | Creating PRs, reading PR status |
| Metadata | Read-only | Required for all Apps (auto-granted) |

Do NOT request: Administration, Workflows, Actions, Packages, Pages, Environments, Deployments, or any Organization permissions.

### GitHub Webhook Event Subscriptions
**Recommendation:** Subscribe to exactly these events:

| Event | Why |
|-------|-----|
| `pull_request` | Track PR opened/closed/merged/review_requested for Discord status updates |
| `installation` | Detect new App installations (backup to polling in /init) |
| `installation_repositories` | Detect repo access changes after initial setup |

Do NOT subscribe to: push, issues (we create them, no need to listen), check_run, check_suite, workflow_run, etc.

### Rate Limit Retry Strategy
**Recommendation:** Use githubkit's built-in retry with these settings:
```python
auto_retry=RetryChainDecision(
    RetryRateLimit(max_retry=3),    # Wait for rate limit reset (reads X-RateLimit-Reset header)
    RetryServerError(max_retry=2),  # Retry 500/502/503 with exponential backoff
)
```
This handles both primary rate limits (5000 req/hour for installations) and secondary rate limits (anti-abuse throttling) automatically.

### Label Color Scheme
**Recommendation:**

| Label | Color (hex) | Description |
|-------|-------------|-------------|
| P1-critical | `e11d48` | Red -- drop everything |
| P2-high | `f97316` | Orange -- this sprint |
| P3-medium | `eab308` | Yellow -- soon |
| P4-low | `22c55e` | Green -- backlog |
| area:* (dynamic) | `6366f1` | Indigo -- code area from AI analysis |
| bot-created | `8b5cf6` | Purple -- marks bot-generated issues |

### Issue Template Format
**Recommendation:**
```markdown
## Bug Report #{hash_id}

**Description:** {description}

**Steps to Reproduce:**
{steps_to_reproduce or "Not provided"}

### Environment
| Field | Value |
|-------|-------|
| Device | {device_info} |
| App Version | {app_version} |
| Severity (reported) | {severity} |

### AI Analysis
- **Root Cause:** {ai_root_cause}
- **Affected Area:** {ai_affected_area}
- **AI Severity:** {ai_severity}
- **Suggested Fix:** {ai_suggested_fix}
- **Priority:** {priority} -- {priority_reasoning}

### Console Logs
<details>
<summary>Click to expand</summary>

```
{console_logs}
```

</details>

---
:link: [Discord Thread](https://discord.com/channels/{guild_id}/{thread_id})
:robot: Created by PreserveFood BugBot
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Personal Access Tokens | GitHub App installation tokens | 2019+ | Fine-grained permissions, auto-rotation, org-level control |
| PyGithub (sync) | githubkit (async + typed) | 2023+ | Native async, typed models from OpenAPI spec, webhook parsing |
| Manual rate limit handling | Built-in RetryChainDecision | githubkit 0.11+ | Handles primary + secondary rate limits automatically |
| Manual webhook HMAC | `githubkit.webhooks.verify()` | githubkit 0.10+ | Time-constant comparison, typed payload models |
| Branch cleanup scripts | `delete_branch_on_merge` repo setting | GitHub 2019 | Automatic, no bot code needed for merge cleanup |

**Deprecated/outdated:**
- PyGithub's `GithubIntegration` class for App auth: works but sync-only and lower-level than githubkit's `AppAuthStrategy`
- gidgethub: still functional but less maintained, no typed models, no webhook parsing

## Database Schema Additions

The following columns and tables need to be added:

### New table: `github_config`
```sql
CREATE TABLE IF NOT EXISTS github_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER UNIQUE NOT NULL,
    installation_id INTEGER NOT NULL,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_config_guild ON github_config(guild_id);
```

### New columns on `bugs` table
```sql
ALTER TABLE bugs ADD COLUMN github_issue_number INTEGER;
ALTER TABLE bugs ADD COLUMN github_issue_url TEXT;
ALTER TABLE bugs ADD COLUMN github_pr_number INTEGER;
ALTER TABLE bugs ADD COLUMN github_pr_url TEXT;
ALTER TABLE bugs ADD COLUMN github_branch_name TEXT;
```

### Environment Variables (new)
```
GITHUB_APP_ID=           # GitHub App ID (numeric)
GITHUB_PRIVATE_KEY=      # RSA private key (PEM format, can be base64-encoded for Docker)
GITHUB_CLIENT_ID=        # GitHub App client ID
GITHUB_CLIENT_SECRET=    # GitHub App client secret
GITHUB_WEBHOOK_SECRET=   # Secret for validating GitHub webhook payloads (SEPARATE from WEBHOOK_SECRET)
```

## Open Questions

1. **Copilot Coding Agent programmatic assignment**
   - What we know: GitHub Copilot coding agent can be assigned to issues manually to auto-generate PRs. The user decision specifies a "hybrid approach" where the bot scaffolds and an external tool fills in code.
   - What's unclear: There is no documented REST API to programmatically assign the Copilot coding agent to an issue. Community discussions suggest assigning via GraphQL does not trigger the agent automatically. This may require manual assignment or a GitHub Actions workflow trigger.
   - Recommendation: Build the PR scaffold (branch + empty PR with full context) as specified. The external tool integration can be handled as a follow-up configuration step. The bot's job is to create the branch and PR -- what fills in the code is an operational concern, not a code concern.

2. **GitHub App callback for /init flow**
   - What we know: GitHub redirects to the "Setup URL" after App installation with `installation_id` as a query param. The user wants a "polling loop" approach.
   - What's unclear: The bot runs inside Docker with an aiohttp server on port 8087. If the Setup URL points to this server, it needs to be publicly accessible. Alternatively, polling `GET /app/installations` avoids needing a public callback endpoint.
   - Recommendation: Use polling approach (no setup URL needed). The `/init` command polls `GET /app/installations` every 5 seconds for up to 5 minutes. This avoids needing the aiohttp server to be publicly reachable for the setup flow. The GitHub webhook endpoint (`/webhook/github`) DOES need to be publicly reachable, but that's a separate concern (already solved for Supabase webhooks on the same port).

3. **Private key storage in Docker**
   - What we know: GitHub App private keys are PEM-formatted RSA keys (~1700 chars). Docker env vars don't handle multi-line values well.
   - What's unclear: Whether to use base64-encoded env var, a mounted file, or Docker secrets.
   - Recommendation: Support both: try reading `GITHUB_PRIVATE_KEY_FILE` (path to .pem file mounted as volume) first, fall back to `GITHUB_PRIVATE_KEY` env var (base64-encoded PEM that gets decoded at startup). This is the standard pattern for Docker deployments.

## Sources

### Primary (HIGH confidence)
- Context7 `/yanyongyu/githubkit` - GitHub App auth, REST API usage, webhook verification, retry configuration, error handling
- GitHub REST API Docs: [Git Refs](https://docs.github.com/en/rest/git/refs) - Branch creation/deletion endpoints and permissions
- GitHub REST API Docs: [Labels](https://docs.github.com/en/rest/issues/labels) - Label creation endpoint
- GitHub REST API Docs: [Permissions](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps) - App permission requirements
- GitHub Docs: [Setup URL](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url) - Post-install redirect behavior
- GitHub Docs: [Auto-delete branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-the-automatic-deletion-of-branches) - `delete_branch_on_merge` setting
- [PyPI GitHubKit](https://pypi.org/project/GitHubKit/) - Version 0.14.4, released 2026-02-08, Python >=3.9

### Secondary (MEDIUM confidence)
- Context7 `/pygithub/pygithub` - PyGithub API patterns (used for comparison, not recommendation)
- GitHub Docs: [Webhook Events](https://docs.github.com/en/webhooks/webhook-events-and-payloads) - Event types and payloads

### Tertiary (LOW confidence)
- GitHub Community Discussions on Copilot coding agent programmatic assignment - Conflicting reports on whether API-based assignment triggers the agent

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - githubkit verified via Context7 (high reputation, score 79.9), PyPI (latest release 2026-02-08), and official docs cross-reference
- Architecture: HIGH - Patterns derived from existing codebase (aiohttp server, discord.py cogs, aiosqlite) + verified githubkit API patterns
- Pitfalls: HIGH - Based on official GitHub docs (rate limits, token expiry, setup URL spoofing) and existing codebase patterns (3-second Discord timeout)
- Discretion items: MEDIUM - Permissions and webhook events based on official docs; label colors and template format are conventional choices

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (30 days -- stable domain, githubkit releases monthly)
