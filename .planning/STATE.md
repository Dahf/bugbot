# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** Bug reports that arrive in Discord get triaged, tracked, and fixed with minimal manual effort
**Current focus:** Phase 3 - GitHub Integration

## Current Position

Phase: 3 of 4 (GitHub Integration)
Plan: 1 of 3 in current phase (03-01 complete)
Status: Executing
Last activity: 2026-02-24 -- Completed 03-01-PLAN.md (GitHub Integration Foundation)

Progress: [██████░░░░] 56%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: ~14 min
- Total execution time: ~1.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-and-ingestion | 2 | ~45 min | ~23 min |
| 02-ai-analysis | 2 | 14 min | 7 min |
| 03-github-integration | 1 | 7 min | 7 min |

**Recent Trend:**
- Last 5 plans: ~40 min, 6 min, 8 min, 7 min
- Trend: Foundation plans fast (7 min avg for Phase 2-3 service layers)

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
- [02-02]: Analyze button defers ephemeral then posts loading message as visible thread message (everyone sees progress)
- [02-02]: Concurrent click guard uses status field: analyzing=in progress, triaged+=already done, dismissed=blocked
- [02-02]: Priority override uses /set-priority slash command (simpler than per-message select menus)
- [02-02]: Thumbs-down reaction tracking is log-only (no feedback DB table yet)
- [02-02]: App commands synced globally on each startup (acceptable for single-guild bot)
- [03-01]: GITHUB_PRIVATE_KEY loaded from file first, then base64 env var, then raw PEM fallback
- [03-01]: github_config uses ON CONFLICT(guild_id) DO UPDATE for upsert semantics
- [03-01]: Console logs in issue body formatted as plain text inside collapsible details block
- [03-01]: Priority label mapping uses first 2 chars (P1/P2/P3/P4) for flexible matching

### Pending Todos

None yet.

### Blockers/Concerns

- Supabase webhook payload schema confirmed via live testing in Phase 1 Plan 02 (blocker resolved)
- githubkit viability verified: v0.14.4 installed, async API working, App auth functional (blocker resolved)

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 03-01-PLAN.md (GitHub Integration Foundation) -- Phase 3 in progress (1/3 plans)
Resume file: None
