---
phase: 02-ai-analysis
plan: 01
subsystem: ai-service, database, discord-embeds
tags: [anthropic, claude-api, async-anthropic, json-parsing, prompt-engineering]

# Dependency graph
requires:
  - phase: 01-01
    provides: Config class, BugRepository CRUD, SQLite schema, embed builders
  - phase: 01-02
    provides: Bug ingestion pipeline, summary embeds, thread detail views
provides:
  - AIAnalysisService class with analyze_bug (Claude API call, structured JSON parsing, token tracking)
  - Database schema with 10 analysis columns and migration for existing Phase 1 DBs
  - BugRepository store_analysis, store_analysis_message_id, update_priority methods
  - build_analysis_embed with severity-coloured sidebar and token usage footer
  - Updated build_summary_embed with conditional priority badge for analyzed bugs
  - SEVERITY_COLORS mapping for analysis embed colour coding
  - Config with optional ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AI_MAX_TOKENS
affects: [02-02-PLAN, ai-analysis-cog, bug-buttons, discord-integration]

# Tech tracking
tech-stack:
  added: [anthropic 0.83.0]
  patterns:
    - service layer separating AI logic from Discord UI
    - structured JSON output from Claude with markdown-fence stripping fallback
    - P1-P4 weighted priority scoring rubric in system prompt
    - idempotent ALTER TABLE migration for schema evolution
    - optional config fields (bot starts without AI key)

key-files:
  created:
    - src/services/__init__.py
    - src/services/ai_analysis.py
  modified:
    - src/config.py
    - src/models/database.py
    - src/models/bug.py
    - src/utils/embeds.py
    - requirements.txt
    - .env.example

key-decisions:
  - "ANTHROPIC_API_KEY is optional -- bot starts without it; AI cog checks at runtime and returns clear error"
  - "Default model is claude-haiku-4-5-20251001 (fastest, cheapest at $1/$5 per MTok)"
  - "JSON parsing has two-stage fallback: direct parse then brace-extraction for markdown-wrapped responses"
  - "Invalid priority values default to P3 with a warning log rather than failing the analysis"
  - "AI service imports _parse_json_field from embeds.py to stay DRY on device_info/console_logs formatting"

patterns-established:
  - "src/services/ package for business logic services separated from Discord cogs"
  - "AIAnalysisService lets API errors propagate to callers for UX-appropriate handling"
  - "SEVERITY_COLORS dict maps AI severity levels to embed colours (separate from STATUS_COLORS)"
  - "migrate_add_analysis_columns() checks PRAGMA table_info before ALTER TABLE for idempotent migration"

requirements-completed: [AI-02, AI-04, AI-07]

# Metrics
duration: 6min
completed: 2026-02-23
---

# Phase 2 Plan 01: AI Analysis Service Layer Summary

**AIAnalysisService with Claude API integration, structured JSON parsing with P1-P4 priority rubric, 10-column DB schema extension with migration, and severity-coloured analysis embed builder**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-23T22:08:08Z
- **Completed:** 2026-02-23T22:14:39Z
- **Tasks:** 3
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments
- AIAnalysisService class with AsyncAnthropic client (60s timeout, 3 retries), structured system prompt with P1-P4 rubric, and robust JSON parsing with markdown-fence fallback
- Database schema extended with 10 analysis columns plus idempotent migration function for existing Phase 1 databases
- Analysis embed builder with severity colour-coded sidebar and token usage footer, plus priority badge on summary embeds for quick scanning

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Anthropic config, extend DB schema, and add analysis CRUD methods** - `e493870` (feat)
2. **Task 2: Create AI analysis service with Claude API integration** - `4fc88d5` (feat)
3. **Task 3: Build analysis embed and update summary embed with priority badge** - `f3e4095` (feat)

## Files Created/Modified
- `src/services/__init__.py` - Package marker for services module
- `src/services/ai_analysis.py` - AIAnalysisService class: Claude API integration, system prompt with P1-P4 rubric, JSON parsing with markdown fallback, token tracking
- `src/config.py` - Added optional ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default haiku-4.5), AI_MAX_TOKENS (default 1024)
- `src/models/database.py` - Extended bugs schema with 10 analysis columns; added migrate_add_analysis_columns() for existing DBs
- `src/models/bug.py` - Added store_analysis (updates all fields + status to triaged), store_analysis_message_id, update_priority methods
- `src/utils/embeds.py` - Added SEVERITY_COLORS mapping, build_analysis_embed function, conditional priority badge in build_summary_embed
- `requirements.txt` - Added anthropic>=0.80.0,<1.0.0
- `.env.example` - Added ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AI_MAX_TOKENS with descriptions

## Decisions Made
- ANTHROPIC_API_KEY is optional (None when not set) -- bot starts without it, AI features check at runtime and return clear errors
- Default model claude-haiku-4-5-20251001 chosen for fastest response time and lowest cost ($1/$5 per MTok) for interactive Discord use
- JSON parsing uses two-stage fallback: direct json.loads then brace extraction for markdown-wrapped responses -- handles Claude's occasional code fence wrapping
- Invalid priority values default to P3 with warning log rather than failing the entire analysis
- AI service imports _parse_json_field from embeds.py to share device_info/console_logs formatting logic (DRY)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

This plan introduces a new external service dependency:

- **Anthropic API Key:** Required for AI analysis features (optional for bot operation)
  - Obtain from: Anthropic Console (https://console.anthropic.com/) -> API Keys -> Create Key
  - Set `ANTHROPIC_API_KEY` in `.env` file
  - Verify with: Bot starts; AI analysis button will function once wired in Plan 02-02

## Next Phase Readiness
- AI service layer, database schema, and embed builders are complete and ready for Plan 02-02
- Plan 02-02 will wire the Analyze button callback to call AIAnalysisService, post the analysis embed in threads, and handle the full Discord UX flow
- The store_analysis, store_analysis_message_id, and update_priority CRUD methods are ready for the cog layer to consume
- All three Analyze/Create Issue/Draft Fix buttons remain disabled from Phase 1; Plan 02-02 enables the Analyze action

## Self-Check: PASSED

- All 8 key files verified present on disk
- All 3 task commits verified in git log (e493870, 4fc88d5, f3e4095)

---
*Phase: 02-ai-analysis*
*Completed: 2026-02-23*
