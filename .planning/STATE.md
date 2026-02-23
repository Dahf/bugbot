# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** Bug reports that arrive in Discord get triaged, tracked, and fixed with minimal manual effort
**Current focus:** Phase 2 - AI Analysis

## Current Position

Phase: 2 of 4 (AI Analysis)
Plan: 1 of 2 in current phase
Status: In Progress
Last activity: 2026-02-23 -- Completed 02-01-PLAN.md (AI Analysis Service Layer)

Progress: [████░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~17 min
- Total execution time: ~0.85 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-and-ingestion | 2 | ~45 min | ~23 min |
| 02-ai-analysis | 1 | 6 min | 6 min |

**Recent Trend:**
- Last 5 plans: 5 min, ~40 min, 6 min
- Trend: Service layer plans execute quickly; UI/integration plans take longer

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Deduplication (AI-05, AI-06) placed in Phase 4 instead of Phase 2 -- requires real analysis data to calibrate similarity thresholds effectively
- [Roadmap]: 4 phases following strict dependency chain (Foundation -> AI -> GitHub -> Intelligence) validated by research
- [01-01]: Used 8-char hex hash IDs (not 4-char) to avoid birthday-problem collisions
- [01-01]: HMAC uses hmac.compare_digest for timing-safe comparison
- [01-01]: Dismissed bugs use [DISMISSED] prefix + grey colour (Discord embeds cannot strikethrough titles)
- [01-01]: Auto-archive duration adapts to server boost level at runtime
- [01-02]: DynamicItem template regex encodes action+bug_id in custom_id for stateless restart survival
- [01-02]: All 4 buttons always visible; Dismiss disables on use, other 3 remain disabled (Phase 2-3)
- [01-02]: Supabase payload maps device_info object and console_logs array to flat DB columns
- [01-02]: Screenshot URL stored and displayed as embed image in summary embed
- [02-01]: ANTHROPIC_API_KEY is optional -- bot starts without it; AI cog checks at runtime
- [02-01]: Default model is claude-haiku-4-5-20251001 (fastest, cheapest for interactive use)
- [02-01]: JSON parsing has two-stage fallback: direct parse then brace-extraction for markdown-wrapped responses
- [02-01]: Invalid AI priority values default to P3 with warning log
- [02-01]: AI service imports _parse_json_field from embeds.py for DRY device/logs formatting

### Pending Todos

None yet.

### Blockers/Concerns

- Supabase webhook payload schema confirmed via live testing in Phase 1 Plan 02 (blocker resolved)
- githubkit viability should be verified (active maintenance, async API coverage) before Phase 3

## Session Continuity

Last session: 2026-02-23
Stopped at: Completed 02-01-PLAN.md (AI Analysis Service Layer) -- Phase 2 Plan 1 of 2
Resume file: None
