# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** Bug reports that arrive in Discord get triaged, tracked, and fixed with minimal manual effort
**Current focus:** Phase 6 in progress -- Developer Context via @Bot Mentions

## Current Position

Phase: 6 of 6 (Developer Context via Bot Mentions)
Plan: 1 of 2 in current phase (06-01 complete)
Status: In Progress
Last activity: 2026-02-25 -- Completed 06-01-PLAN.md (Developer notes data layer, cog, and bot wiring)

Progress: [█████████░] 92%

## Performance Metrics

**Velocity:**
- Total plans completed: 12
- Average duration: ~9 min
- Total execution time: ~1.8 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-and-ingestion | 2 | ~45 min | ~23 min |
| 02-ai-analysis | 2 | 14 min | 7 min |
| 03-github-integration | 4 | 24 min | 6 min |
| 05-ai-code-fix | 3 | 14 min | 5 min |
| 06-developer-context-via-bot-mentions | 1 | 5 min | 5 min |

**Recent Trend:**
- Last 5 plans: 3 min, 3 min, 7 min, 4 min, 5 min
- Trend: Stable 3-7 min execution times

*Updated after each plan completion*
| Phase 03 P03 | 7min | 2 tasks | 6 files |
| Phase 03 P04 | 3min | 2 tasks | 3 files |
| Phase 05 P01 | 3min | 2 tasks | 2 files |
| Phase 05 P02 | 7min | 2 tasks | 1 files |
| Phase 05 P03 | 4min | 2 tasks | 3 files |
| Phase 06 P01 | 5min | 2 tasks | 6 files |

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
- [03-02]: /init polling uses set-difference approach (snapshot known IDs before polling, detect new by diff)
- [03-02]: RepoSelectView with discord.ui.Select for multi-repo case, auto-select for single repo
- [03-02]: Create Issue button enabled only when analyzed=True AND issue_created=False
- [03-02]: _handle_create_issue does NOT revert status on failure (issue may be partially created on GitHub)
- [03-03]: Branch naming convention: bot/bug-{hash_id}-{slug} with 30-char slug limit
- [03-03]: Draft Fix re-trigger blocked with link to existing branch/PR
- [03-03]: build_pr_body handles optional issue_number -- Closes #N only when issue exists
- [03-03]: _derive_bug_flags helper centralises status-to-flag mapping for all build_bug_view callers
- [03-03]: Webhook handlers use non-blocking Discord operations (errors logged, 200 returned to GitHub)
- [03-04]: Keyword overlap scoring for file identification -- simple heuristic, not full RAG
- [03-04]: Context file committed at .bugbot/context.md on feature branch (namespaced directory)
- [03-04]: Each new Draft Fix step (7a, 7b, 7c) individually try/except wrapped for graceful degradation
- [03-04]: Source file snippets limited to 200 lines in context commit, 50KB max per file in read_repo_files
- [05-01]: Default code fix model is claude-sonnet-4-5-20250929 (good balance of quality and cost for code generation)
- [05-01]: CI polling uses initial delay + second-chance retry before declaring no_ci
- [05-01]: Installation token extracted via apps.async_create_installation_access_token
- [05-02]: Tool definitions use closure factory (_create_tools) with @beta_async_tool to bind clone_dir and share mutable state
- [05-02]: Quality gates run in strict sequence (lint -> self-review -> CI) with early exit on failure
- [05-02]: Self-review uses same model as code generation with lower max_tokens (1024)
- [05-02]: On all-rounds-exhausted, best attempt is committed anyway per locked user decision
- [05-02]: Linter detection checks pyproject.toml for ruff first, then config file map, with shutil.which guard
- [05-03]: build_code_fix_pr_body is separate from build_pr_body to preserve backward compatibility with scaffold PRs
- [05-03]: Completion embed uses green for full validation pass, yellow for partial
- [05-03]: Failed code fix still creates PR if files were changed (best-attempt approach)
- [05-03]: Progress callback posts wrench emoji prefix messages in thread for visual consistency
- [06-01]: DeveloperNotesRepository defines helpers locally rather than importing from bug.py to avoid tight coupling
- [06-01]: Attachment URLs stored as JSON array string consistent with console_logs pattern
- [06-01]: Role check on @mention silently ignores non-developers (no error reply) to avoid noise
- [06-01]: Summary embed counter update is non-fatal (try/except) so note saving never fails due to embed issues
- [06-01]: No changes to bug_buttons.py -- note_count passed separately to build_summary_embed by callers

### Roadmap Evolution

- Phase 5 added: AI Code Fix — Agentic multi-step code generation im Draft Fix Flow
- Phase 6 added: Developer Context via @Bot Mentions

### Pending Todos

None yet.

### Blockers/Concerns

- Supabase webhook payload schema confirmed via live testing in Phase 1 Plan 02 (blocker resolved)
- githubkit viability verified: v0.14.4 installed, async API working, App auth functional (blocker resolved)

## Session Continuity

Last session: 2026-02-25
Stopped at: Completed 06-01-PLAN.md (Developer notes data layer, cog, and bot wiring)
Resume file: None
