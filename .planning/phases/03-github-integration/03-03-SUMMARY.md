---
phase: 03-github-integration
plan: 03
subsystem: api
tags: [github, branches, pull-requests, webhooks, draft-fix, auto-resolve]

# Dependency graph
requires:
  - phase: 03-github-integration
    provides: "GitHubService with App auth, GitHubConfigRepository, issue/PR templates, /init command, Create Issue button"
  - phase: 02-ai-analysis
    provides: "AI analysis fields on bugs table for PR body context"
  - phase: 01-foundation-and-ingestion
    provides: "BugRepository, BugActionButton DynamicItem, build_bug_view, summary embed builder"
provides:
  - "Draft Fix button creating feature branches and PR scaffolds from default branch"
  - "GitHub webhook endpoint /webhook/github with signature verification"
  - "Auto-resolve on PR merge with branch cleanup and Discord embed update"
  - "PR lifecycle notifications in bug threads (merge, close, review_requested)"
  - "store_github_pr, get_bug_by_branch_name, get_bug_by_github_issue on BugRepository"
  - "create_branch, create_pull_request, delete_branch, get_default_branch_sha on GitHubService"
  - "_derive_bug_flags helper for consistent button state derivation"
affects: [04-intelligence-layer]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Branch creation via git.async_create_ref (never touches default branch)", "Webhook signature validation via githubkit.webhooks.verify", "Non-blocking Discord operations in webhook handlers (log errors, never raise)", "Centralised flag derivation (_derive_bug_flags) for button state consistency"]

key-files:
  created: []
  modified:
    - src/services/github_service.py
    - src/views/bug_buttons.py
    - src/models/bug.py
    - src/cogs/github_integration.py
    - src/cogs/webhook.py
    - src/utils/github_templates.py

key-decisions:
  - "Branch naming convention: bot/bug-{hash_id}-{slug} with 30-char slug limit"
  - "Draft Fix re-trigger blocked with link to existing branch/PR (not silent, not overwrite)"
  - "build_pr_body updated to handle optional issue_number -- Closes #N only when issue exists"
  - "_derive_bug_flags helper centralises status-to-flag mapping for all build_bug_view callers"
  - "Webhook handlers use non-blocking Discord operations (errors logged, 200 returned to GitHub)"

patterns-established:
  - "Branch naming: bot/bug-{id}-{slug} -- slugified, truncated, unique per bug"
  - "Centralised flag derivation: _derive_bug_flags(bug) -> kwargs for build_bug_view"
  - "Webhook event routing: webhook.py validates, github_integration.py dispatches by event type"
  - "Non-blocking Discord in webhooks: try/except around all Discord API calls, log errors"

requirements-completed: [GH-04, GH-05, GH-06, GH-07, GH-08, GH-10]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 3 Plan 03: Draft Fix Button and Webhook Event Handlers Summary

**Draft Fix button creating feature branches and PR scaffolds with full bug context, GitHub webhook handlers auto-resolving bugs on PR merge with branch cleanup and Discord notifications**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T10:11:30Z
- **Completed:** 2026-02-24T10:19:09Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Draft Fix button creates a feature branch from the default branch and opens a PR scaffold with full bug context, AI analysis, Discord thread link, and Closes #N (GH-04, GH-05, GH-06, GH-07, GH-08)
- GitHub webhook endpoint at /webhook/github validates signatures with GITHUB_WEBHOOK_SECRET (separate from Supabase secret per Pitfall 5)
- PR merge auto-resolves bugs, deletes the feature branch, updates the Discord embed to "resolved", and posts a notification in the bug thread (GH-10)
- PR close without merge and review_requested events post notifications in bug threads without changing status
- Re-triggering Draft Fix on a bug with an existing branch/PR is blocked with a helpful message linking to the existing PR

## Task Commits

Each task was committed atomically:

1. **Task 1: Add branch and PR creation methods to GitHub service and enable Draft Fix button** - `fe3e951` (feat)
2. **Task 2: Add GitHub webhook route and PR lifecycle event handlers** - `1ff4794` (feat)

## Files Created/Modified
- `src/services/github_service.py` - Added create_branch, create_pull_request, delete_branch, get_default_branch_sha, build_branch_name methods
- `src/views/bug_buttons.py` - Implemented _handle_draft_fix callback, added fix_drafted parameter to build_bug_view, added _derive_bug_flags helper
- `src/models/bug.py` - Added store_github_pr, get_bug_by_branch_name, get_bug_by_github_issue methods
- `src/utils/github_templates.py` - Updated build_pr_body to handle optional issue_number and discord_thread_url
- `src/cogs/webhook.py` - Added /webhook/github route with githubkit signature verification
- `src/cogs/github_integration.py` - Added handle_github_event, handle_pull_request_event, _update_discord_embed, _post_thread_message methods

## Decisions Made
- **Branch naming**: `bot/bug-{hash_id}-{slug}` with the title slugified (lowercase, non-alphanumeric replaced with hyphens, truncated to 30 chars). This keeps branch names readable and unique per bug.
- **Re-trigger blocking**: When Draft Fix is clicked on a bug that already has a branch, the user gets a message with the existing branch name and PR URL. This prevents duplicate branches/PRs.
- **Optional Closes #N**: The PR body only includes `Closes #N` when the bug has a linked GitHub issue. Bugs can have PRs without issues (Draft Fix is available after analysis, not just after Create Issue).
- **Centralised flag derivation**: Added `_derive_bug_flags(bug)` helper that all callers of `build_bug_view` use, ensuring consistent button state logic across dismiss, analyze, create_issue, and draft_fix handlers.
- **Non-blocking Discord ops in webhooks**: All Discord API calls in webhook handlers are wrapped in try/except. Errors are logged but never raised, ensuring GitHub always receives 200 and doesn't retry.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

To receive GitHub webhook events, the GitHub App's webhook URL must be configured to point to `{bot_host}:{port}/webhook/github` and the `GITHUB_WEBHOOK_SECRET` environment variable must be set to match the App's webhook secret.

## Next Phase Readiness
- Full GitHub integration loop is complete: bug -> analyze -> create issue -> draft fix -> PR merged -> auto-resolved
- Phase 3 (GitHub Integration) is fully complete with all 3 plans executed
- Ready for Phase 4 (Intelligence Layer) which builds on the analysis and GitHub data

## Self-Check: PASSED

- All 6 modified files verified present on disk
- Both task commits (fe3e951, 1ff4794) verified in git log

---
*Phase: 03-github-integration*
*Completed: 2026-02-24*
