---
phase: 03-github-integration
plan: 01
subsystem: api
tags: [github, githubkit, github-app, oauth, sqlite, markdown-templates]

# Dependency graph
requires:
  - phase: 01-foundation-and-ingestion
    provides: "SQLite database, Config class, aiosqlite models, bug CRUD"
  - phase: 02-ai-analysis
    provides: "AI analysis fields on bugs table (ai_root_cause, ai_affected_area, etc.)"
provides:
  - "GitHubService with App auth and rate limit retry"
  - "GitHubConfigRepository for per-guild repo settings"
  - "Issue and PR markdown template builders"
  - "GitHub env var loading in Config (all optional)"
  - "github_config table and bugs GitHub columns"
affects: [03-github-integration]

# Tech tracking
tech-stack:
  added: ["githubkit[auth-app]>=0.14.0,<1.0.0", "aiohttp>=3.9.0,<4.0.0"]
  patterns: ["GitHub App auth via AppAuthStrategy with auto-retry", "Installation-scoped clients for repo operations", "Optional env var pattern (bot works without GitHub config)"]

key-files:
  created:
    - src/services/github_service.py
    - src/models/github_config.py
    - src/utils/github_templates.py
  modified:
    - src/config.py
    - src/models/database.py
    - requirements.txt

key-decisions:
  - "GITHUB_PRIVATE_KEY loaded from file first, then base64 env var, then raw PEM fallback"
  - "github_config uses ON CONFLICT(guild_id) DO UPDATE for upsert semantics"
  - "Console logs in issue body formatted as plain text inside collapsible details block"
  - "Priority label mapping uses first 2 chars (P1/P2/P3/P4) for flexible matching"

patterns-established:
  - "GitHub App auth: AppAuthStrategy with RetryChainDecision(RetryRateLimit, RetryServerError)"
  - "Installation client: get_installation_client(owner, repo) returns scoped GitHub client"
  - "Optional integration: Config.github_configured property gates feature availability"
  - "Template builders: standalone functions that take bug dict and return markdown string"

requirements-completed: [GH-09]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 3 Plan 01: GitHub Integration Foundation Summary

**GitHub App auth service with githubkit, per-guild repo config in SQLite, and markdown template builders for issue/PR bodies**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T09:46:43Z
- **Completed:** 2026-02-24T09:53:36Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- GitHubService authenticates as a GitHub App with auto-retry for rate limits and server errors (GH-09)
- Per-guild GitHub configuration stored in SQLite with full CRUD via GitHubConfigRepository
- Issue body templates include all bug context: description, steps, environment, AI analysis, console logs, Discord thread link
- PR body templates include bug summary, AI analysis, auto-close reference, and external tool note
- All GitHub env vars are optional -- bot starts and works normally without GitHub integration

## Task Commits

Each task was committed atomically:

1. **Task 1: Add GitHub config, database schema, and per-guild config model** - `8bcbe41` (feat)
2. **Task 2: Create GitHub service with App auth and markdown templates** - `4687afd` (feat)

## Files Created/Modified
- `requirements.txt` - Added githubkit[auth-app] and aiohttp dependencies
- `src/config.py` - Added GitHub App env vars (APP_ID, PRIVATE_KEY, CLIENT_ID, CLIENT_SECRET, WEBHOOK_SECRET, APP_NAME) and github_configured property
- `src/models/database.py` - Added github_config table schema and migrate_add_github_columns migration for bugs table
- `src/models/github_config.py` - NEW: GitHubConfigRepository with get/set/delete for per-guild repo configuration
- `src/services/github_service.py` - NEW: GitHubService with AppAuthStrategy, installation client, installation listing
- `src/utils/github_templates.py` - NEW: build_issue_body, build_pr_body, label helpers (priority, area, bot-created)

## Decisions Made
- **Private key loading**: GITHUB_PRIVATE_KEY_FILE (path) takes priority over GITHUB_PRIVATE_KEY (base64 env var). If the env var is not valid base64, it is returned as-is (raw PEM string). This supports both Docker volume mounts and env var injection.
- **Upsert for guild config**: GitHubConfigRepository.set_config uses ON CONFLICT(guild_id) DO UPDATE instead of INSERT OR REPLACE, preserving the original created_at timestamp on updates.
- **Console log formatting**: Issue body uses plain text `[LEVEL] message` format inside a collapsible details block, rather than Discord emoji formatting, for clean GitHub rendering.
- **Priority label matching**: get_priority_label matches on first 2 characters (P1/P2/P3/P4) so it works with both "P1" and "P1-critical" input formats.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None for this plan - GitHub App credentials will be needed when enabling the integration in a later plan. The `user_setup` section in the plan frontmatter documents the full GitHub App creation process.

## Next Phase Readiness
- GitHubService ready for issue creation (Plan 02) and PR scaffolding (Plan 03)
- GitHubConfigRepository ready for /init command to store per-guild repo settings
- Template builders ready for Create Issue and Draft Fix button handlers
- All imports verified, no circular dependencies

## Self-Check: PASSED

- All 6 files verified present on disk
- Both task commits (8bcbe41, 4687afd) verified in git log

---
*Phase: 03-github-integration*
*Completed: 2026-02-24*
