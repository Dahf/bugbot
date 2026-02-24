---
phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow
plan: 02
subsystem: api
tags: [anthropic, tool-runner, beta-async-tool, agentic-loop, code-generation, lint, ci-polling, clone]

# Dependency graph
requires:
  - phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow
    provides: GitHubService extensions (commit_files_atomic, poll_ci_status, get_installation_token) and code fix config env vars
  - phase: 03-github-integration
    provides: GitHubService with installation auth, branch/PR operations
provides:
  - CodeFixService agentic code fix orchestrator with clone, generate, validate, iterate loop
  - 4 @beta_async_tool definitions (read_file, write_file, search_in_repo, list_directory) for Claude repo exploration
  - Quality gates: linter detection/execution, AI self-review, CI polling
  - Main generate_fix entry point with progress callback for Discord
affects: [05-03, draft-fix-button, bug-buttons, pr-body-builder]

# Tech tracking
tech-stack:
  added: []
  patterns: [agentic-tool-runner-loop, beta-async-tool-closure-factory, multi-round-quality-gate-pipeline]

key-files:
  created:
    - src/services/code_fix_service.py
  modified: []

key-decisions:
  - "Tool definitions use closure factory (_create_tools) to bind clone_dir and share mutable state (changed_files set, files_read_count list)"
  - "Linter detection checks pyproject.toml for ruff first, then falls through config file map, with shutil.which guard before execution"
  - "AI self-review uses same model as code generation with lower max_tokens (1024) and JSON response format"
  - "Each quality gate short-circuits to next round on failure -- lint -> self-review -> CI in strict sequence"
  - "Final commit uses best_changed_files from last round regardless of validation outcome (submit best attempt per locked decision)"

patterns-established:
  - "Agentic loop pattern: tool_runner with @beta_async_tool closure-bound tools, single until_done() call per round"
  - "Quality gate pipeline: lint -> self-review -> CI in sequence, feedback dict passed to next round for targeted corrections"
  - "Clone lifecycle: mkdtemp + shallow clone in clone_repo, onerror chmod cleanup in finally block"
  - "Progress callback pattern: async callable injected into generate_fix for decoupled Discord messaging"

requirements-completed: [GH-04, GH-05, GH-06]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 05 Plan 02: CodeFixService Agentic Code Generation Engine Summary

**Agentic code fix orchestrator using Anthropic tool_runner with 4 @beta_async_tool repo exploration tools, 3-round quality gate pipeline (lint/self-review/CI), and atomic commit via GitHubService**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T13:41:16Z
- **Completed:** 2026-02-24T13:48:40Z
- **Tasks:** 2
- **Files created:** 1

## Accomplishments
- CodeFixService class with complete agentic code generation loop: clone repo, let Claude explore and fix code via 4 tool functions, validate through 3 quality gates, iterate up to 3 rounds
- Tool factory (_create_tools) using @beta_async_tool decorator with closure-bound clone_dir, changed_files tracking, and files_read_count cap (15 files default)
- Linter detection supporting ruff, flake8, pylint, eslint, cargo clippy, and go vet with shutil.which guard and 60s execution timeout
- AI self-review against correctness, side-effects, and code style criteria with JSON response parsing and graceful fallback
- Main generate_fix orchestration method with progress callback, try/finally cleanup, and structured result dict

## Task Commits

Each task was committed atomically:

1. **Task 1: Create CodeFixService with repo cloning and agentic tool definitions** - `981b61e` (feat)
2. **Task 2: Add quality gates and main orchestration method** - `acdf74b` (feat)

## Files Created/Modified
- `src/services/code_fix_service.py` - New 816-line agentic code fix orchestrator with CodeFixService class, _create_tools factory, and _LINTER_CONFIGS map

## Decisions Made
- Tool definitions use a closure factory pattern rather than class methods -- enables @beta_async_tool decorator on standalone async functions while sharing mutable state (changed_files set, files_read_count)
- Linter detection checks pyproject.toml [tool.ruff] section first (most common Python linter), then falls through a config file map for other linters
- Self-review uses the same model as code generation but with 1024 max_tokens (review needs less output than code generation)
- Quality gates run in strict sequence (lint -> self-review -> CI) with early exit on failure -- no point running CI if lint fails
- On all-rounds-exhausted, best_changed_files is committed anyway per the locked user decision ("submit the best attempt with a note")

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. CodeFixService uses the same ANTHROPIC_API_KEY already configured for AI analysis, plus the Phase 5 config vars added in Plan 01.

## Next Phase Readiness
- CodeFixService provides the complete generate_fix entry point needed by Plan 03 (Draft Fix button integration)
- Progress callback pattern is ready for Discord thread progress messages
- Process log structure is ready for PR body collapsible section
- All quality gate feedback types (lint, self_review, ci) are handled with specific prompts for each

---
*Phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow*
*Completed: 2026-02-24*

## Self-Check: PASSED
- Source file exists: src/services/code_fix_service.py (816 lines)
- Task 1 commit verified: 981b61e
- Task 2 commit verified: acdf74b
- SUMMARY.md created
