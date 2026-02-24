---
phase: 03-github-integration
plan: 02
subsystem: api
tags: [github, discord, slash-command, issue-creation, labels, buttons, embeds]

# Dependency graph
requires:
  - phase: 03-github-integration
    provides: "GitHubService with App auth, GitHubConfigRepository, issue/PR templates, label helpers"
  - phase: 02-ai-analysis
    provides: "AI analysis fields on bugs table (priority, ai_affected_area, etc.) for labels and issue body"
  - phase: 01-foundation-and-ingestion
    provides: "BugRepository, BugActionButton DynamicItem, build_bug_view, summary embed builder"
provides:
  - "/init slash command with polling-based GitHub App installation flow"
  - "Create Issue button callback with full issue creation workflow"
  - "Auto-created GitHub labels (priority, area, bot-created)"
  - "Summary embed with GitHub Issue and Pull Request link fields"
  - "store_github_issue method for triaged -> issue_created status transition"
  - "ensure_labels and create_issue methods on GitHubService"
affects: [03-github-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Polling loop for GitHub App install detection (avoids public callback URL)", "Label ensure-then-create pattern (idempotent label creation)", "Button state gating via build_bug_view parameters (analyzed, issue_created)"]

key-files:
  created:
    - src/cogs/github_integration.py
  modified:
    - src/bot.py
    - src/services/github_service.py
    - src/models/bug.py
    - src/views/bug_buttons.py
    - src/utils/embeds.py

key-decisions:
  - "Polling loop uses set-difference approach: snapshot known installation IDs before polling, detect new by comparing"
  - "RepoSelectView with discord.ui.Select for multi-repo case, auto-select for single repo"
  - "Create Issue button enabled only when analyzed=True AND issue_created=False"
  - "Error handling in _handle_create_issue wraps entire GitHub API section, does NOT revert status on failure"

patterns-established:
  - "Slash command cog pattern: @app_commands.command with defer then followup"
  - "Label ensure pattern: try create, catch 422 (already exists) silently"
  - "Button state progression: dismissed -> analyzed -> issue_created as gating parameters"

requirements-completed: [GH-01, GH-02, GH-03]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 3 Plan 02: /init Command and Create Issue Button Summary

**/init slash command with polling-based GitHub App setup, Create Issue button creating labeled GitHub issues with full bug context and Discord thread backlinks**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T09:58:38Z
- **Completed:** 2026-02-24T10:05:11Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- /init slash command walks users through GitHub App installation with a 5-minute polling loop, repo selection dropdown, and stored per-guild config
- Create Issue button creates well-structured GitHub issues with priority labels (P1-P4), area labels, and bot-created label -- all auto-created if missing (GH-01)
- Issue body includes full bug context: description, steps, environment, AI analysis, console logs, and Discord thread link (GH-02, GH-03)
- Summary embed now displays clickable GitHub Issue and Pull Request links when they exist
- Button state progression: Create Issue enabled only for analyzed bugs without existing issues

## Task Commits

Each task was committed atomically:

1. **Task 1: Create /init slash command and wire GitHub service into bot** - `f37d7ff` (feat)
2. **Task 2: Enable Create Issue button with full issue creation flow** - `bd9f2c2` (feat)
3. **Task 3: Add GitHub issue link to summary embed and update embed refresh logic** - `419fd48` (feat)

## Files Created/Modified
- `src/cogs/github_integration.py` - NEW: /init slash command cog with polling loop, repo selection view, and setup confirmation
- `src/bot.py` - Added GitHubService and GitHubConfigRepository initialization in setup_hook, added github_integration to cog list, added cleanup in close()
- `src/services/github_service.py` - Added ensure_labels (idempotent label creation) and create_issue (issue creation with labels) methods
- `src/models/bug.py` - Added store_github_issue method for persisting issue number/URL and transitioning to issue_created status
- `src/views/bug_buttons.py` - Implemented _handle_create_issue callback, updated build_bug_view with issue_created parameter, routed create_issue action to handler
- `src/utils/embeds.py` - Added conditional GitHub Issue and Pull Request fields to summary embed

## Decisions Made
- **Polling approach for /init**: Uses set-difference detection (snapshot known installation IDs before polling, new = current - known). This avoids needing a public callback URL for the setup flow and prevents setup URL spoofing (Pitfall 3 from RESEARCH.md).
- **RepoSelectView**: When multiple repos are accessible to the installation, a discord.ui.Select dropdown is presented (max 25 options, 120s timeout). Single-repo case auto-selects.
- **Create Issue button gating**: Enabled only when `analyzed=True` AND `issue_created=False`. This prevents creating issues for unanalyzed bugs and duplicates.
- **Error handling**: The _handle_create_issue callback wraps all GitHub API calls in a single try/except. On failure, status is NOT reverted because the issue might have been partially created on GitHub's side.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None for this plan -- GitHub App credentials must already be configured (documented in Plan 01). The /init command guides users through the GitHub App installation after credentials are set.

## Next Phase Readiness
- Create Issue flow is complete and ready for production use
- Summary embed already supports Pull Request links (prepared for Plan 03 Draft Fix)
- GitHubService has ensure_labels pattern ready for reuse in PR creation
- build_bug_view accepts issue_created parameter, ready for Draft Fix button enablement
- All imports verified, no circular dependencies

## Self-Check: PASSED

- All 6 files verified present on disk
- All 3 task commits (f37d7ff, bd9f2c2, 419fd48) verified in git log

---
*Phase: 03-github-integration*
*Completed: 2026-02-24*
