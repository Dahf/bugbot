---
phase: 06-developer-context-via-bot-mentions
plan: 01
subsystem: database, discord-cog
tags: [sqlite, discord.py, cog, crud, slash-command, mentions]

# Dependency graph
requires:
  - phase: 01-foundation-and-ingestion
    provides: "BugRepository pattern, database.py migration pattern, bug_buttons.py view builder"
  - phase: 02-ai-analysis
    provides: "ai_analysis.py cog pattern for slash commands"
provides:
  - "developer_notes SQLite table with migration"
  - "DeveloperNotesRepository with full CRUD (create, get, count, update, delete)"
  - "BugRepository.get_bug_by_thread_id for thread-to-bug lookups"
  - "DeveloperNotesCog with on_message, raw edit/delete listeners, /view-notes command"
  - "message_content intent enabled in bot.py"
  - "build_summary_embed note_count parameter and counter field"
affects: [06-developer-context-via-bot-mentions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw event listeners (on_raw_message_edit, on_raw_message_delete) for syncing DB with Discord message lifecycle"
    - "Bot mention stripping with dual format (<@ID> and <@!ID>) for content extraction"
    - "Optional keyword parameter on build_summary_embed for additive embed fields"

key-files:
  created:
    - src/models/developer_notes.py
    - src/cogs/developer_notes.py
  modified:
    - src/models/database.py
    - src/models/bug.py
    - src/bot.py
    - src/utils/embeds.py

key-decisions:
  - "DeveloperNotesRepository reuses _utcnow_iso and _row_to_dict locally rather than importing from bug.py to avoid tight coupling"
  - "Attachment URLs stored as JSON array string consistent with console_logs pattern"
  - "Role check on @mention silently ignores non-developers (no error message) to avoid noise"
  - "Embed counter update is non-fatal (try/except) so note saving never fails due to embed issues"
  - "No changes to bug_buttons.py -- note_count passed separately to build_summary_embed by callers that have it"

patterns-established:
  - "Raw event listener pattern: on_raw_message_edit/delete for syncing external data with Discord message lifecycle"
  - "Mention stripping pattern: dual-format removal (<@ID> and <@!ID>) then strip"

requirements-completed: [DEV-01, DEV-02, DEV-03, DEV-04, DEV-05]

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 6 Plan 01: Developer Context via Bot Mentions Summary

**DeveloperNotesCog with @mention note saving, edit/delete sync, /view-notes command, and summary embed notes counter backed by SQLite developer_notes table**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T09:25:21Z
- **Completed:** 2026-02-25T09:29:53Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- developer_notes table with full migration, indexes on bug_id, message_id, and bugs.thread_id
- DeveloperNotesRepository with 6 CRUD methods (create, get_notes_for_bug, count_notes, get_note_by_message_id, update_note_by_message_id, delete_note_by_message_id)
- DeveloperNotesCog handling @mentions in bug threads with role gating, help message for empty mentions, pencil reaction, note count reply, and embed counter update
- Edit/delete sync via raw event listeners keeping DB in sync with Discord message lifecycle
- /view-notes slash command showing all notes in an ephemeral embed
- message_content intent enabled and notes_repo wired in bot.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Database schema, DeveloperNotesRepository, and BugRepository extension** - `e407c31` (feat)
2. **Task 2: DeveloperNotesCog, bot.py wiring, and summary embed notes counter** - `141913a` (feat)

## Files Created/Modified
- `src/models/developer_notes.py` - DeveloperNotesRepository with full CRUD for developer notes
- `src/cogs/developer_notes.py` - DeveloperNotesCog with on_message, raw edit/delete, /view-notes
- `src/models/database.py` - developer_notes table schema, migration, idx_bugs_thread_id index
- `src/models/bug.py` - get_bug_by_thread_id method on BugRepository
- `src/bot.py` - message_content intent, notes_repo init, developer_notes cog loading
- `src/utils/embeds.py` - note_count parameter on build_summary_embed with counter field

## Decisions Made
- DeveloperNotesRepository defines _utcnow_iso and _row_to_dict locally rather than importing from bug.py to avoid tight coupling between models
- Attachment URLs stored as JSON array string consistent with the console_logs storage pattern
- Role check on @mention silently ignores non-developers (no error reply) to avoid channel noise
- Summary embed counter update wrapped in try/except so note saving never fails due to embed issues
- No changes needed to bug_buttons.py -- note_count is passed separately to build_summary_embed by callers that have it

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

**External services require manual configuration:**
- Enable **Message Content Intent** in Discord Developer Portal -> Bot Application -> Bot -> Privileged Gateway Intents -> Message Content Intent

## Next Phase Readiness
- Data layer and cog complete, ready for Phase 6 Plan 02 (testing, error edge cases, or additional features)
- Message Content Intent must be enabled in Discord Developer Portal before bot can read @mention text

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 06-developer-context-via-bot-mentions*
*Completed: 2026-02-25*
