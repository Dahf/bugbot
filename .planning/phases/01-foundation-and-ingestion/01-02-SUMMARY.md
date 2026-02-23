---
phase: 01-foundation-and-ingestion
plan: 02
subsystem: webhook-ingestion, discord-ui, database
tags: [aiohttp, discord.py, dynamicitem, sqlite, hmac, supabase]

# Dependency graph
requires:
  - phase: 01-01
    provides: BugBot class, Config, BugRepository CRUD, HMAC auth, embed builders, SQLite schema
provides:
  - aiohttp WebhookServer Cog with HMAC-validated /webhook/bug-report endpoint
  - BugReports Cog with async queue consumer posting summary embeds and creating threads
  - DynamicItem BugActionButton with role gating, dismiss handler, and restart persistence
  - Full end-to-end pipeline: webhook POST -> stored in DB -> embed in Discord -> thread -> interactive buttons
  - Supabase edge function payload adapter (device_info object, console_logs array, screenshot_url)
affects: [02-ai-analysis, phase-3-github, phase-4-intelligence]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - store-then-process (return 200 immediately, enqueue for async Discord posting)
    - DynamicItem with regex template for persistent custom_ids surviving bot restarts
    - timeout=None views for button persistence
    - role gating via interaction_check before callback execution

key-files:
  created:
    - src/cogs/webhook.py
    - src/cogs/bug_reports.py
    - src/views/bug_buttons.py
  modified:
    - src/bot.py
    - src/models/bug.py
    - src/models/database.py
    - src/utils/embeds.py

key-decisions:
  - "DynamicItem template regex bug:(?P<action>\\w+):(?P<bug_id>[a-f0-9]+) encodes action+bug_id in custom_id for stateless restart survival"
  - "Dismiss button disabled after use; Analyze/Create Issue/Draft Fix remain disabled (Phase 2-3); all 4 buttons always visible"
  - "Supabase payload maps device_info {platform, osVersion} object and console_logs [{level, message}] array to flat DB columns"
  - "Screenshot URL from Supabase stored and displayed as embed image in summary embed"
  - "Title derived from description substring when explicit title field absent in Supabase payload"

patterns-established:
  - "Cog lifecycle: cog_load() starts background task/server, cog_unload() cancels/stops cleanly"
  - "Queue-based decoupling: webhook handler enqueues hash_id, process_loop consumes asynchronously"
  - "DynamicItem from_custom_id as factory method extracting state from regex match groups"
  - "build_bug_view(bug_id, dismissed=False) helper centralises button state logic"

requirements-completed: [FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-06, FOUND-08]

# Metrics
duration: ~40min
completed: 2026-02-23
---

# Phase 1 Plan 02: Webhook Ingestion and Discord UI Summary

**aiohttp webhook server with HMAC validation, async queue-driven embed/thread posting, and DynamicItem dismiss buttons with role gating that survive bot restarts**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-02-23T20:48:00Z
- **Completed:** 2026-02-23T22:26:00Z
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint)
- **Files modified:** 7

## Accomplishments
- aiohttp WebhookServer Cog validates HMAC signatures and immediately returns 200 while enqueuing the bug_id for async processing
- BugReports Cog consumes the queue, posts colour-coded summary embeds to the configured channel, auto-creates threads with full bug details, and stores Discord message/thread references in the DB
- DynamicItem BugActionButton persists across bot restarts via regex template custom_ids and setup_hook registration; Dismiss updates DB, refreshes embed to grey, disables only the Dismiss button, and confirms in thread
- Supabase edge function payload structure adapted: device_info object, console_logs array, screenshot image in embed, title derived from description

## Task Commits

Each task was committed atomically:

1. **Task 1: Create webhook server cog and bug processing cog** - `1ade35b` (feat)
2. **Task 2: Implement DynamicItem buttons with role gating and dismiss handler** - `012f1a2` (feat)
3. **Task 3: Verify end-to-end webhook-to-Discord flow** - User approved checkpoint (no files)

**Post-plan fixes:**
- `356e21d` fix(01): adapt bot for Supabase edge function payload structure
- `911a405` feat(01-02): add screenshot image to summary embed

## Files Created/Modified
- `src/cogs/webhook.py` - aiohttp WebhookServer Cog: /webhook/bug-report with HMAC validation, /health endpoint, store-then-process pattern
- `src/cogs/bug_reports.py` - BugReports Cog: async queue consumer, embed posting, thread creation with full details, message ref storage
- `src/views/bug_buttons.py` - BugActionButton DynamicItem: regex template, role gating, dismiss handler, build_bug_view helper
- `src/bot.py` - Wired up new cogs in setup_hook; added DynamicItem registration and BugRepository init
- `src/models/bug.py` - Adapted for Supabase payload: device_info object, console_logs array, reporter_name, screenshot_url fields
- `src/models/database.py` - Added reporter_name and screenshot_url columns to bugs table schema
- `src/utils/embeds.py` - Updated summary embed and thread detail for Supabase payload structure; added screenshot image to embed

## Decisions Made
- DynamicItem with regex template chosen for button persistence over storing view state in DB -- stateless approach, state read from DB on each interaction
- All four buttons remain visible after Dismiss (none hidden or removed) per CONTEXT.md decision
- Dismiss button disabled after use; the other three remain disabled as they were -- no state change for them
- Supabase payload structure adapted as deviation (Rule 1 bug fix) when live testing revealed mismatched field names

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Adapted parser for Supabase edge function payload structure**
- **Found during:** Task 3 (end-to-end verification)
- **Issue:** Supabase webhook payload sends `device_info` as a JSON object `{platform, osVersion}` and `console_logs` as an array of `{level, message}` objects. The original embed builders and DB model expected flat string fields, causing parsing errors and missing data.
- **Fix:** Updated `src/models/bug.py` to flatten the object/array fields on store, added `reporter_name` and `screenshot_url` columns, derived `title` from description substring when absent. Updated `src/utils/embeds.py` to format the structured fields and display `screenshot_url` as the embed image.
- **Files modified:** src/models/bug.py, src/models/database.py, src/utils/embeds.py, src/cogs/bug_reports.py
- **Verification:** Live end-to-end test with real Supabase webhook confirmed embed displays correctly with all fields populated
- **Committed in:** 356e21d, 911a405

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in payload parsing)
**Impact on plan:** Essential fix -- without it the embed was empty/broken for real Supabase payloads. No scope creep.

## Issues Encountered
- Supabase edge function sends a different payload shape than the flat structure anticipated during planning. Fixed inline during verification without blocking progress.

## User Setup Required

None - configuration was already established in Plan 01-01. The webhook secret and Discord channel ID were configured in the existing `.env` file.

## Next Phase Readiness
- Complete ingestion pipeline is operational: Supabase bug reports arrive via webhook, are stored in SQLite, displayed as Discord embeds with threads, and have working interactive buttons
- Phase 2 (AI Analysis) can build on top of the existing BugRepository and extend the button callback for the Analyze action
- The Analyze/Create Issue/Draft Fix buttons are already wired in with graceful "coming soon" fallbacks -- Phase 2 only needs to implement the callbacks
- Blocker resolved: Supabase webhook payload schema is now confirmed from live testing

## Self-Check: PASSED

- All 7 key files verified present on disk
- All 4 task/fix commits verified in git log (1ade35b, 012f1a2, 356e21d, 911a405)

---
*Phase: 01-foundation-and-ingestion*
*Completed: 2026-02-23*
