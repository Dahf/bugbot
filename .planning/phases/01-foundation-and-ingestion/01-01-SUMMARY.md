---
phase: 01-foundation-and-ingestion
plan: 01
subsystem: database, bot-core, utilities
tags: [discord.py, aiosqlite, sqlite, hmac, python-dotenv]

# Dependency graph
requires:
  - phase: none
    provides: first plan -- no dependencies
provides:
  - BugBot class with setup_hook and clean shutdown
  - Config class loading from environment variables
  - SQLite database schema (bugs + status_history tables)
  - BugRepository with full CRUD (create, get, update_status, list, mark_dismissed, store_raw_report)
  - HMAC-SHA256 webhook signature validation
  - Summary embed builder with colour-coded statuses
  - Thread detail message builder with N/A fallbacks
  - Hash ID generation with collision checking
  - Thread name and auto-archive helpers
affects: [01-02-PLAN, webhook-ingestion, discord-embeds, buttons]

# Tech tracking
tech-stack:
  added: [discord.py 2.6.4, aiosqlite 0.22.1, python-dotenv 1.2.1, aiohttp 3.13.3]
  patterns: [store-then-process, cog-based architecture, status colour mapping, parameterised SQL]

key-files:
  created:
    - src/bot.py
    - src/config.py
    - src/models/database.py
    - src/models/bug.py
    - src/utils/hashing.py
    - src/utils/webhook_auth.py
    - src/utils/embeds.py
    - requirements.txt
    - .env.example
    - .gitignore
  modified: []

key-decisions:
  - "Used 8-char hex hash IDs (secrets.token_hex(4)) for ~4 billion combinations to avoid birthday-problem collisions"
  - "HMAC validation uses hmac.compare_digest for timing-safe comparison"
  - "Summary embed shows ONLY title, status, severity, reporter -- full details in thread"
  - "Dismissed bugs get [DISMISSED] title prefix and grey colour since Discord embeds cannot strikethrough titles"
  - "Auto-archive duration adapts at runtime to server boost level (1/3/7 days)"

patterns-established:
  - "Config class with _require() for mandatory env vars and sensible defaults for optional ones"
  - "BugRepository class wrapping aiosqlite.Connection for all bug CRUD"
  - "status_history table for audit trail of all status changes"
  - "STATUS_COLORS and STATUS_EMOJI dicts as single source of truth for status presentation"
  - "Thread detail messages use N/A fallbacks and console log truncation at 1500 chars"

requirements-completed: [FOUND-05, FOUND-07, FOUND-08]

# Metrics
duration: 5min
completed: 2026-02-23
---

# Phase 1 Plan 01: Project Foundation Summary

**BugBot skeleton with Config, SQLite schema (bugs + status_history), BugRepository CRUD, HMAC webhook auth, and colour-coded embed builders**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-23T20:38:17Z
- **Completed:** 2026-02-23T20:43:21Z
- **Tasks:** 3
- **Files modified:** 17 (10 created in Task 1, 2 in Task 2, 2 in Task 3, plus 5 __init__.py)

## Accomplishments
- Project skeleton with all directories, dependencies installed, and environment config
- SQLite database with WAL mode, bugs and status_history tables, and full BugRepository CRUD
- Utility functions: 8-char collision-safe hash IDs, timing-safe HMAC validation, colour-coded summary embeds, thread detail messages with truncation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create project skeleton with configuration and bot entry point** - `2b9f4a8` (feat)
2. **Task 2: Implement SQLite database schema and bug model with CRUD operations** - `98ae873` (feat)
3. **Task 3: Build utility functions -- hash generation, HMAC auth, and embed builders** - `7f58e4b` (feat)

## Files Created/Modified
- `src/bot.py` - BugBot class with setup_hook, on_ready, clean shutdown
- `src/config.py` - Config class loading from env vars with validation
- `src/models/database.py` - SQLite schema creation with WAL mode and foreign keys
- `src/models/bug.py` - BugRepository with create, get, update_status, list, mark_dismissed, store_raw_report
- `src/utils/hashing.py` - generate_hash_id with 8-char hex IDs and collision checking
- `src/utils/webhook_auth.py` - HMAC-SHA256 validation with timing-safe comparison
- `src/utils/embeds.py` - Summary embed, thread detail message, thread name, auto-archive helpers
- `requirements.txt` - discord.py, aiosqlite, python-dotenv
- `.env.example` - All configurable environment variables with descriptions
- `.gitignore` - Python/IDE/data exclusions

## Decisions Made
- Used 8-char hex hash IDs (not 4-char) to avoid birthday-problem collisions per RESEARCH.md pitfall 7
- HMAC uses hmac.compare_digest (not ==) for timing-safe comparison
- Summary embed shows only title/status/severity/reporter per CONTEXT.md decisions
- Dismissed bugs use [DISMISSED] prefix + grey colour since Discord embed titles cannot be struck through
- Auto-archive duration adapts to server boost level at runtime rather than hardcoding 7 days

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required for this plan. External services (Discord bot token, webhook secret) will be needed when running the bot, but that setup belongs to Plan 01-02.

## Next Phase Readiness
- Bot skeleton, database layer, and all utility functions are ready for Plan 01-02
- Plan 01-02 can build webhook ingestion, Discord embeds/threads/buttons, and dismiss handler on top of this foundation
- All imports and module boundaries are established -- cog extensions are expected by bot.py but gracefully handled when missing

## Self-Check: PASSED

- All 10 created files verified present on disk
- All 3 task commits verified in git log (2b9f4a8, 98ae873, 7f58e4b)

---
*Phase: 01-foundation-and-ingestion*
*Completed: 2026-02-23*
