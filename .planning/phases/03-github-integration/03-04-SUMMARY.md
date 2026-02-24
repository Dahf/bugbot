---
phase: 03-github-integration
plan: 04
subsystem: api
tags: [github, source-files, context-commit, draft-fix, pr-enrichment]

# Dependency graph
requires:
  - phase: 03-github-integration
    provides: "GitHubService with branch/PR creation, Draft Fix button, build_pr_body template"
  - phase: 02-ai-analysis
    provides: "ai_affected_area, ai_root_cause, ai_suggested_fix fields on bugs table"
  - phase: 01-foundation-and-ingestion
    provides: "BugRepository, BugActionButton DynamicItem, build_bug_view"
provides:
  - "read_repo_files method for fetching and decoding source files from GitHub repos"
  - "commit_context_file method for committing files to feature branches"
  - "identify_relevant_files method with keyword-based file scoring heuristic"
  - "build_context_commit_content template for .bugbot/context.md branch commits"
  - "Enhanced build_pr_body with source file references and context commit note"
  - "Full Draft Fix flow: identify files -> read files -> commit context -> open enriched PR"
affects: [04-intelligence-layer]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Keyword overlap scoring for file relevance (split affected area into words, match against file paths)", "Graceful degradation via individual try/except on non-critical steps (7a, 7b, 7c)", "Base64 encode/decode for GitHub Contents API file reading and commit creation", "Context file committed to .bugbot/ directory on feature branch for external tool consumption"]

key-files:
  created: []
  modified:
    - src/services/github_service.py
    - src/utils/github_templates.py
    - src/views/bug_buttons.py

key-decisions:
  - "Keyword overlap scoring for file identification -- simple heuristic, not full RAG (per Out of Scope in REQUIREMENTS.md)"
  - "Context file path is .bugbot/context.md -- namespaced directory keeps bot artifacts separate"
  - "Each new Draft Fix step (7a, 7b, 7c) is individually try/except wrapped for graceful degradation"
  - "Source file snippets limited to 200 lines in context commit, 50KB max per file in read_repo_files"
  - "PR body references file paths with line counts but not full content (full content in committed .bugbot/context.md)"

patterns-established:
  - "Non-fatal enrichment steps: wrap optional API calls in try/except, log warning, continue with empty defaults"
  - ".bugbot/ directory convention for bot-generated files on feature branches"
  - "Top-5 keyword scoring for file relevance identification"

requirements-completed: [GH-04, GH-05, GH-06]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 3 Plan 04: Gap Closure -- Source File Reading, Context Commits, and Enriched PR Body Summary

**Draft Fix reads relevant source files via keyword scoring, commits structured .bugbot/context.md to the feature branch, and enriches PR body with file references for external tools**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T10:40:45Z
- **Completed:** 2026-02-24T10:43:53Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Draft Fix now identifies relevant source files from the repo using keyword overlap between AI-identified affected area and file paths, reads their contents, and commits a structured `.bugbot/context.md` to the feature branch before opening the PR
- PR body includes a "Relevant Source Files" section listing identified files with line counts, and the scaffold note references the committed context file
- All three new steps (identify, read, commit) degrade gracefully -- if any fails, the Draft Fix still creates the PR scaffold as before
- GH-04 (AI-drafted scaffold with source context), GH-05 (source file reading), and GH-06 (commits to feature branch) verification gaps are closed

## Task Commits

Each task was committed atomically:

1. **Task 1: Add repo file reading and context commit methods to GitHubService** - `f28dcff` (feat)
2. **Task 2: Integrate file reading and context commit into Draft Fix flow** - `88fe2d8` (feat)

## Files Created/Modified
- `src/services/github_service.py` - Added read_repo_files, commit_context_file, identify_relevant_files methods with base64 handling, error resilience, and keyword scoring
- `src/utils/github_templates.py` - Added build_context_commit_content function, enhanced build_pr_body with source_files parameter and .bugbot/context.md reference
- `src/views/bug_buttons.py` - Added steps 7a/7b/7c to _handle_draft_fix (identify, read, commit), imported build_context_commit_content, passed source_files to build_pr_body

## Decisions Made
- **Keyword overlap scoring**: Split ai_affected_area into lowercase words, count matches against lowercase file paths (including directory names). Simple but effective for the most common cases. Not full RAG per REQUIREMENTS.md Out of Scope.
- **Context file at .bugbot/context.md**: Namespaced under .bugbot/ to keep bot artifacts separate from project source code on the feature branch.
- **Individual try/except per step**: Steps 7a, 7b, and 7c each have their own try/except so a failure in one does not prevent the others. If all three fail, the PR is still created (just without enrichment).
- **200-line snippet limit**: Source file content in the committed context file is truncated to 200 lines to keep commit size manageable.
- **50KB file size limit**: Files larger than 50KB are truncated in read_repo_files to avoid excessive API data transfer.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no new external service configuration required. All new functionality uses the existing GitHub App installation authentication.

## Next Phase Readiness
- Phase 3 (GitHub Integration) gap closure complete: all GH-04/GH-05/GH-06 verification gaps are now closed
- The full Draft Fix flow is: analyze bug -> identify relevant files -> read source code -> commit context to branch -> create enriched PR
- Ready for Phase 4 (Intelligence Layer) which builds on the analysis and GitHub data

## Self-Check: PASSED

- `src/services/github_service.py` verified present on disk with read_repo_files, commit_context_file, identify_relevant_files methods
- `src/utils/github_templates.py` verified present on disk with build_context_commit_content function and enhanced build_pr_body
- `src/views/bug_buttons.py` verified present on disk with steps 7a/7b/7c in _handle_draft_fix
- Task 1 commit (f28dcff) verified in git log
- Task 2 commit (88fe2d8) verified in git log

---
*Phase: 03-github-integration*
*Completed: 2026-02-24*
