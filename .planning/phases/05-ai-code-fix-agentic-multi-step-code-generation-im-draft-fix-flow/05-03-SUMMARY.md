---
phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow
plan: 03
subsystem: ui
tags: [discord-buttons, draft-fix, code-fix-integration, pr-template, process-log, completion-embed]

# Dependency graph
requires:
  - phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow
    provides: CodeFixService with generate_fix entry point, progress callback, and structured result
  - phase: 03-github-integration
    provides: GitHubService with branch/PR operations, Draft Fix button handler scaffold
provides:
  - Rewritten Draft Fix button handler calling CodeFixService agentic loop
  - Live progress messages in Discord thread during code fix generation
  - Rich completion embed with files changed, rounds, validation, token usage
  - Collapsible process log section in PR body with per-round quality gate results
  - CodeFixService initialization in bot.py setup_hook
affects: [end-to-end-flow, pr-body-format, discord-ux]

# Tech tracking
tech-stack:
  added: []
  patterns: [progress-callback-discord-thread, completion-embed-with-quality-gates, collapsible-process-log-pr-body]

key-files:
  created: []
  modified:
    - src/utils/github_templates.py
    - src/views/bug_buttons.py
    - src/bot.py

key-decisions:
  - "build_code_fix_pr_body is a separate function from build_pr_body to preserve backward compatibility with scaffold PRs"
  - "Completion embed uses green (0x22c55e) for full validation pass, yellow (0xeab308) for partial"
  - "Failed code fix still creates PR if any files were changed (submit best attempt per locked decision)"
  - "Progress callback posts wrench emoji prefix messages in thread for visual consistency"

patterns-established:
  - "Progress callback pattern: async callable injected into service, posts to Discord thread with try/except guard"
  - "Completion embed pattern: color-coded embed with fields for changed files, rounds, validation, PR link, and token footer"
  - "Process log collapsible section: HTML details block with per-round lint/review/CI status using emoji indicators"

requirements-completed: [GH-04, GH-05, GH-06]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 05 Plan 03: Draft Fix Integration with CodeFixService Summary

**Rewritten Draft Fix button handler calling CodeFixService agentic loop with live Discord progress, rich completion embed, and collapsible process log in PR body**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T13:53:43Z
- **Completed:** 2026-02-24T13:57:57Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added `build_process_log_section` and `build_code_fix_pr_body` template functions for AI code fix PRs with collapsible process logs and per-round quality gate results
- Rewrote `_handle_draft_fix` to call `CodeFixService.generate_fix` with live progress callback posting to Discord thread
- Added CodeFixService initialization in `bot.py` `setup_hook` when both ANTHROPIC_API_KEY and GitHub are configured
- Added rich completion embed posted in thread with files changed, rounds taken, validation status, PR link, failed gates, and token usage footer

## Task Commits

Each task was committed atomically:

1. **Task 1: Add process log builder and code fix PR body template to github_templates.py** - `1f6b602` (feat)
2. **Task 2: Initialize CodeFixService in bot.py and rewrite _handle_draft_fix** - `3f8d23e` (feat)

## Files Created/Modified
- `src/utils/github_templates.py` - Added build_process_log_section (collapsible HTML details with per-round lint/review/CI) and build_code_fix_pr_body (full PR body with changes, validation warning, process log)
- `src/views/bug_buttons.py` - Rewrote _handle_draft_fix to use CodeFixService with progress callback, completion embed, and code fix PR body; added build_code_fix_pr_body import
- `src/bot.py` - Added CodeFixService import, code_fix_service attribute, and initialization in setup_hook

## Decisions Made
- `build_code_fix_pr_body` is a new separate function -- existing `build_pr_body` preserved unchanged for scaffold PRs used by other code paths
- Completion embed color-coded: green (0x22c55e) when all quality gates pass, yellow (0xeab308) when validation is partial
- If code fix generation fails but some files were changed, PR is still created (best-attempt approach per locked decision from 05-02)
- Progress messages use wrench emoji prefix for visual consistency with the Draft Fix action

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Uses the same ANTHROPIC_API_KEY and GitHub credentials already configured. Phase 5 config vars (model, max_rounds, etc.) were added in Plan 01.

## Next Phase Readiness
- Phase 5 is now complete: the full pipeline is connected end-to-end
- Draft Fix button -> CodeFixService agentic loop -> quality gates -> atomic commit -> PR with process log
- Live progress feedback in Discord thread keeps users informed during multi-minute code generation
- All guard checks (status, re-trigger, service availability) are preserved from the original handler
- The system is ready for production testing with real bug reports

---
*Phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow*
*Completed: 2026-02-24*

## Self-Check: PASSED
- All 3 source files exist (github_templates.py, bug_buttons.py, bot.py)
- All 2 task commits verified (1f6b602, 3f8d23e)
- SUMMARY.md created
