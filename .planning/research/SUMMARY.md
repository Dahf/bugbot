# Project Research Summary

**Project:** PreserveFood Discord Bot
**Domain:** AI-powered bug triage Discord bot with GitHub automation
**Researched:** 2026-02-23
**Confidence:** MEDIUM

## Executive Summary

The PreserveFood Discord Bot is an internal developer tool that automates the journey from user-submitted bug reports (delivered via Supabase webhook) to analyzed GitHub issues and AI-drafted pull requests. Expert practice for this class of project converges on a single-process async Python architecture: discord.py handles the Discord gateway, aiohttp co-hosts the webhook listener on the same event loop, and a clean service layer sits between both entry points and the external APIs (Claude, GitHub). SQLite is the right database — zero infrastructure, survives restarts with a Docker volume, and easily handles the projected volume of a few reports per week. This is emphatically not a microservices problem; all three research areas independently affirmed the single-process monolith.

The recommended approach is to build in four meaningful phases: first establish a solid async foundation with webhook ingestion and Discord display; then add AI analysis; then add GitHub issue and PR creation; then add intelligence features like deduplication, the bug dashboard, and release notes. Each phase delivers standalone value and provides the foundation the next phase requires. The high-complexity AI code generation features belong in Phase 3 only after the data pipeline and state management are battle-tested — debugging AI code generation on top of a fragile bot is significantly more expensive than building the plumbing correctly first.

The two most dangerous risks in this project are architectural: (1) blocking the Discord event loop with synchronous API calls, which causes the bot to disconnect silently and fail all interactions, and (2) Discord interaction token expiration (15-minute window) breaking multi-step workflows that span AI analysis plus GitHub operations. Both must be resolved at the architecture level before any feature code is written. A third risk — AI-generated code committing to the wrong branch or leaking secrets — is a Phase 3 concern but requires design decisions in Phase 1 (GitHub token scoping, branch protection enforced in code).

## Key Findings

### Recommended Stack

The stack is Python 3.12+ with discord.py (>=2.3) as the bot framework and the official anthropic SDK (>=0.39) using `AsyncAnthropic` for Claude calls. aiohttp serves double duty as discord.py's transitive HTTP dependency and as the webhook server — this avoids adding a second HTTP framework for a single POST endpoint and ensures both servers share one event loop naturally. githubkit replaces PyGithub as the GitHub API client because PyGithub is synchronous-only, which is a dealbreaker in an async bot where each PR workflow requires 4-6 sequential API calls. SQLite via aiosqlite covers all persistence needs at projected volume. Pydantic v2 validates every external data boundary.

For quality tooling, ruff replaces the flake8+black+isort trio, mypy enforces type correctness, and pytest-asyncio enables testing async handlers. The entire stack runs in a single Docker container with a mounted volume for SQLite persistence. See STACK.md for full rationale and alternatives considered.

**Core technologies:**
- **Python 3.12+**: Runtime — specializing interpreter, mature asyncio, full library support
- **discord.py >=2.3**: Discord bot framework — dominant library, fully async, built-in buttons/views/threads
- **anthropic >=0.39**: Claude API client — official SDK, `AsyncAnthropic` for non-blocking calls
- **aiohttp >=3.9**: Webhook HTTP server — already a discord.py dependency, shares event loop natively
- **githubkit >=0.11**: GitHub API client — async-native, auto-generated from OpenAPI spec
- **aiosqlite >=0.20**: Database — async SQLite wrapper, zero infrastructure overhead
- **pydantic >=2.5**: Data models — validates webhook payloads, API responses, and config at boundaries
- **tenacity >=8.2**: Retry logic — exponential backoff for GitHub and Claude transient failures
- **structlog >=24.1**: Logging — JSON-formatted, context-bound logs for correlating async flows

**Version caveat:** All version numbers are MEDIUM confidence based on training data. Verify against PyPI before installing.

### Expected Features

**Must have (table stakes):**
- Webhook ingestion and parsing — the entire input pipeline; without it nothing works
- Rich embed display of bug reports — formatted, color-coded, scannable in Discord
- Per-ticket Discord threads — isolates discussions; a single channel is unusable beyond 5 open bugs
- Button-based actions (Create Issue, Analyze, Dismiss) — project chose buttons over slash commands
- Persistent state (SQLite) — survives restarts; users expect continuity
- Status tracking per bug — state machine: received -> analyzing -> triaged -> issue_created -> fix_drafted -> resolved
- AI bug analysis — the core value proposition; without it this is just a webhook relay
- GitHub issue creation — the first automation output; links Discord triage to the code tracker
- Basic error handling and resilience — retry logic, graceful degradation; a silent bot is worse than no bot

**Should have (differentiators):**
- Smart deduplication — prevents 5 issues for the same crash; conservative thresholds, human fallback for ambiguous matches
- Priority scoring — automated P1-P4 based on crash type, user frequency, and affected area
- Bug dashboard embed — persistent at-a-glance view sorted by priority
- Codebase context injection — prerequisite for useful AI fixes (required before AI code generation)
- AI-drafted code fixes — the leap from triage tool to fix accelerator
- Automated PR creation — closes the loop from report to reviewable code change
- Assignment/ownership — needed when collaborators join

**Defer (v2+):**
- Auto-generated release notes — depends on PR workflow being stable first
- Thread summary on resolution — low complexity, not blocking
- Web dashboard, natural language commands, complex RBAC, auto-merge, codebase RAG indexing — explicitly out of scope

See FEATURES.md for full dependency chain and complexity estimates.

### Architecture Approach

The recommended pattern is a **Dual-Server Async Monolith with Service Layer**: one Python process, one asyncio event loop, two concurrent async servers (discord.py gateway + aiohttp webhook listener), and a service layer that both entry points call into. The Discord Bot and Webhook Server never call GitHub or Claude directly — they delegate to services. Services never import discord.py types — they return plain Pydantic models that the Discord UI layer converts to embeds and views. This separation is what makes the bot testable and maintainable as it grows. See ARCHITECTURE.md for full component diagram and data flow sequences.

**Major components:**
1. **Discord Bot (Cogs)** — gateway connection, button/command handlers, thread management, embed rendering; organized as discord.py Cogs from day one
2. **Webhook Server (aiohttp)** — HTTP endpoint for Supabase, signature validation, payload parsing, emits custom events via `bot.dispatch()`
3. **Bug Triage Service** — bug lifecycle state machine, deduplication logic, priority scoring
4. **AI Analysis Service** — Claude API wrapper, prompt management, structured response parsing, code generation
5. **GitHub Automation Service** — issue CRUD, branch creation, file operations, PR creation
6. **Data Layer (SQLite repositories)** — the only component that touches the database; repository pattern
7. **Discord UI Layer (Views/Embeds)** — Persistent Views with `custom_id`-encoded state, embed builders with truncation helpers

**Critical pattern — Persistent Views:** All discord.py Views must use `timeout=None` with stable `custom_id` values encoding state as `action:bug_id`. Views must be re-registered in `setup_hook`. Without this, every bot restart makes all existing message buttons non-functional.

**Critical pattern — Interaction deferral:** Every button callback must call `await interaction.response.defer()` within 3 seconds, then communicate progress via the per-ticket thread (not interaction follow-ups). The 15-minute interaction token window does not survive a full AI-analysis plus GitHub PR workflow.

### Critical Pitfalls

1. **Blocking the event loop with synchronous API calls** — Use `AsyncAnthropic` not `Anthropic`, aiohttp for HTTP, never `requests`. Every external call must be awaited. Failure mode: bot disconnects silently and all interactions fail with a 3-second timeout. Must be architecturally correct from the first line of code.

2. **Interaction token expiration (15-minute window)** — Use the thread as the communication channel, not the interaction follow-up. Defer immediately, post progress as regular thread messages. Track in-progress operations to reject duplicate button clicks before they create duplicate GitHub issues or PRs.

3. **Unauthenticated webhook endpoint** — Validate a shared secret on every request (custom header). Implement idempotency (store processed IDs, return 200 for duplicates without re-processing). Rate-limit the endpoint. Sanitize Discord mentions (@everyone, @here) from user content before posting.

4. **Discord View state lost on restart** — Implement Persistent Views with `custom_id`-encoded state from the first button. Store all workflow state in SQLite, never in-memory. Test by restarting the bot after every new button implementation.

5. **AI-generated code safety** — Never commit to main/master (enforce in code, not convention). Sanitize AI output for secrets. Scope file modifications in the prompt and validate the diff against expected files. Validate syntax before committing. Use a fine-grained GitHub PAT scoped to one repo with minimal permissions.

6. **GitHub API rate limiting causing partial workflows** — Queue GitHub operations (max 2-3 concurrent). Implement retry with `Retry-After` header handling for both 429 and 403 secondary rate limits. Make the issue -> branch -> commit -> PR workflow transactional (clean up partial state on failure).

7. **Claude API cost explosion** — Set `max_tokens` on every call (analysis: 1-2K tokens, code generation: 4-8K). Log token usage after every call. Cache analysis results. Use two-pass context injection: first pass identifies relevant files cheaply, second pass sends only those sections.

See PITFALLS.md for 8 additional moderate and minor pitfalls with phase-specific warnings.

## Implications for Roadmap

All three research files (FEATURES.md, ARCHITECTURE.md, PITFALLS.md) independently converged on a consistent phase structure driven by hard component dependencies and risk management. The roadmap should reflect this.

### Phase 1: Foundation and Ingestion

**Rationale:** Everything depends on config, a running bot, working persistence, and authenticated webhook ingestion. Five of the fifteen researched pitfalls are Phase 1 concerns. Getting the dual-server async architecture wrong here means a near-rewrite — it cannot be retrofitted.

**Delivers:** A running Discord bot that receives Supabase webhook payloads, displays formatted bug report embeds with placeholder action buttons, persists reports to SQLite, and survives restarts with all buttons still functional.

**Addresses:** Webhook ingestion, rich embed display, per-ticket threads, persistent state, status tracking, config and secret management.

**Avoids:**
- Async event loop blocking — aiohttp co-hosted on same event loop, async-first architecture throughout (Pitfall 1)
- View state lost on restart — Persistent Views with `custom_id`-encoded state from the first button (Pitfall 7)
- Dual-server event loop conflict — aiohttp started inside `setup_hook` or as a background task (Pitfall 8)
- Unauthenticated webhook — secret validation + idempotency from the first endpoint (Pitfall 4)
- Leaked secrets — .gitignore and fine-grained tokens before any functional code (Pitfall 10)
- Embed limit crashes — truncation helpers built before any embed rendering (Pitfall 11)

**Research needed:** Supabase webhook payload schema must be confirmed with the mobile app team before webhook parsing is implemented.

### Phase 2: AI Analysis Layer

**Rationale:** AI analysis is the core value proposition and the prerequisite for deduplication, priority scoring, and everything in Phase 3. This is also where the primary API cost risk lives — token budgeting and usage logging must be established here, not added later.

**Delivers:** Automated AI analysis on every incoming bug report. Priority scoring (P1-P4). Button-driven Analyze action with deferred interaction handling and progress updates posted to the bug thread. AI analysis results embedded in Discord display.

**Addresses:** Button-based actions (fully wired with deferred responses), AI bug analysis, priority scoring, basic error handling and resilience.

**Avoids:**
- Interaction token expiration — thread-based communication pattern, interaction deferred immediately (Pitfall 2)
- Cost explosion — max_tokens set on every call, usage logged, analysis results cached (Pitfall 6)
- Prompt injection — XML-delimited user content in all prompt templates (Pitfall 12)
- Graceful degradation — store-then-process webhook pattern; if AI is down, raw report is still posted to Discord (Pitfall 13)
- Thread explosion — thread lifecycle and archival strategy designed before creating the first thread (Pitfall 14)

**Research needed:** Claude structured output patterns for parsing bug analysis into typed Pydantic models. Verify the exact `AsyncAnthropic` API for streaming vs. non-streaming structured responses.

### Phase 3: GitHub Integration and Code Generation

**Rationale:** GitHub operations depend on AI analysis — issues are created from analysis results, fixes require analysis context. This phase carries the highest external API complexity: rate limits, multi-step sequential workflows, and branch management. The code safety guardrails (never commit to main, sanitize output) must be in place before any code is pushed.

**Delivers:** Create GitHub Issue button (from analysis output, linked to Discord thread). Draft Fix button (AI code generation with repo context, branch creation, PR creation). Automated PR with structured description linking back to Discord thread and GitHub issue.

**Addresses:** GitHub issue creation (table stakes), codebase context injection (prerequisite for fixes), AI-drafted code fixes (differentiator), automated PR creation (differentiator).

**Avoids:**
- AI code safety — branch naming convention enforced in code, output sanitization for secrets, syntax validation before commit (Pitfall 3)
- Rate limiting — queued GitHub operations, retry with backoff for both 429 and 403 secondary limits, transactional workflow cleanup (Pitfall 5)
- Merge conflicts and stale branches — always branch from latest HEAD, delete merged branches via API, flag conflicts in Discord for human resolution (Pitfall 15)

**Research needed:** githubkit async API surface for the full create-branch -> commit-files -> open-PR flow. Verify current API signatures against githubkit documentation. Claude code generation prompt design for producing clean, scoped diffs will require empirical iteration.

### Phase 4: Intelligence and Polish

**Rationale:** These features enhance the core workflow but are not on the critical path. Smart deduplication is placed here (not Phase 2) deliberately — it requires reliable analysis output to produce meaningful similarity comparisons, and calibrating dedup thresholds requires real data from the Phase 2-3 pipeline.

**Delivers:** Smart deduplication with conservative thresholds and human fallback for uncertain matches. Bug dashboard embed with priority-sorted open bugs. Assignment/ownership for team scaling. Auto-generated release notes from merged PRs. Thread archival on resolution.

**Addresses:** Smart deduplication, bug dashboard embed, assignment/ownership, auto-generated release notes, thread summary on resolution.

**Avoids:**
- Dedup false positives — start with conservative thresholds; prefer false negatives over false positives; human confirmation button for uncertain matches (Pitfall 9)
- Thread explosion — auto-archive resolved threads via Discord API, periodic cleanup task (Pitfall 14)

### Phase Ordering Rationale

- **Dependency chain is strict:** Webhook -> Analysis -> GitHub -> Intelligence. Collapsing phases sacrifices foundation quality.
- **Pitfall front-loading:** 7 of the 10 most critical pitfalls manifest in Phases 1-2. Addressing them early prevents Phase 3 rewrites.
- **Risk escalation is intentional:** Phase 3's AI code generation is the highest-risk feature. By the time it is built, the async patterns, error handling, retry logic, and state management are all proven.
- **Each phase is independently useful:** A Phase 1 bot (ingestion + display) is useful. A Phase 2 bot (analysis + priority) saves meaningful triage time. A Phase 3 bot (GitHub automation) accelerates the fix cycle. Phase 4 adds intelligence on top of a proven system.

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 3 (GitHub Integration):** The multi-step PR workflow using githubkit's async API needs verification against current docs. Secondary rate limit behavior (403 vs 429) should be confirmed. githubkit is less mainstream — verify active maintenance before committing to it; the fallback is `httpx.AsyncClient` with direct REST calls.
- **Phase 3 (AI Code Generation):** Prompt engineering for code fix generation producing reviewer-friendly diffs is domain-specific. Plan for prompt iteration — the first prompts will not produce review-ready PRs.
- **Phase 4 (Deduplication):** The right similarity algorithm and threshold require calibration against real bug reports. Build this late because real data is required.

Phases with standard patterns (skip or minimize research-phase):

- **Phase 1 (Foundation):** discord.py Cogs, Persistent Views, aiohttp co-hosting, SQLite schema, and .env configuration are well-documented patterns with abundant examples.
- **Phase 2 (AI Analysis):** AsyncAnthropic usage, structured output prompting, and interaction deferral are established patterns with official SDK documentation. Prompt templates will need tuning but the integration pattern is straightforward.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Architectural recommendations (which library and why) are HIGH — stable ecosystem patterns. Specific version numbers are MEDIUM — training data, unverified against live PyPI. githubkit is the least mainstream choice; verify continued maintenance before Phase 1. |
| Features | MEDIUM | Table stakes features are HIGH — derived from project scope and well-established Discord bot UX. Differentiator complexity estimates are MEDIUM — actual AI prompt quality for code generation is unpredictable without implementation. |
| Architecture | MEDIUM | Core patterns (Cog-per-feature, Persistent Views, aiohttp co-hosting, service layer) are HIGH — documented discord.py v2.x patterns. Specific API signatures should be verified against current discord.py docs before implementation. |
| Pitfalls | MEDIUM-HIGH | Critical pitfalls (event loop blocking, interaction token expiry, Persistent Views) are thoroughly documented in discord.py community resources. Specific limit values (3-second acknowledgment window, 15-minute token lifetime, 1000 threads per channel) should be verified against current Discord API docs. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Supabase webhook payload schema:** The bot is designed around a stable Supabase webhook contract, but the exact payload schema is not documented in the research. Must be confirmed with the mobile app team before Phase 1 webhook parsing is implemented. This is a blocking dependency.

- **githubkit viability:** githubkit is the recommended async GitHub client but is less mainstream than PyGithub. Verify it is actively maintained and covers branch creation, file commits, and PR creation before committing to it. If maintenance is uncertain, the fallback is `httpx.AsyncClient` with direct GitHub REST API calls — more verbose but no external dependency risk.

- **Claude code generation prompt quality:** Research describes the approach but cannot predict the quality of AI-generated diffs. Plan for prompt iteration in Phase 3. The first AI-generated PRs will require significant prompt engineering before they are reviewer-friendly.

- **Library version numbers:** All versions must be verified against PyPI before writing pyproject.toml. Key packages to check: discord.py (is 2.x still the stable line?), githubkit (latest stable, actively maintained?), anthropic (any breaking changes since training cutoff?), pydantic (v2 still current?).

- **Discord gateway intents:** The exact intent configuration required for threads, buttons, embeds, and message content access must be confirmed against current Discord developer documentation. Over-broad intents require Discord bot verification for large servers.

- **pydantic-settings integration:** pydantic-settings is a separate package from pydantic v2 required for environment variable loading into typed config models. Add it to the dependency list and verify the import path before Phase 1 config implementation.

## Sources

### Primary (HIGH confidence)
- discord.py documentation: https://discordpy.readthedocs.io/ — Cog system, Persistent Views, interaction handling, embed limits, thread management
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python — AsyncAnthropic client, structured output, tool use
- GitHub REST API documentation — issue/PR/branch operations, rate limits, secondary rate limits
- General async Python patterns — asyncio event loop management, aiohttp co-hosting, non-blocking patterns

### Secondary (MEDIUM confidence)
- githubkit: https://github.com/yanyongyu/githubkit — async GitHub client, OpenAPI-generated models
- aiosqlite: https://github.com/omnilib/aiosqlite — async SQLite wrapper
- Pydantic v2: https://docs.pydantic.dev/ — model validation, settings management
- Discord bot UX patterns — buttons vs. slash commands, thread design, embed design, deduplication approaches

### Tertiary (LOW confidence — verify before use)
- Specific library version numbers — all from training data cutoff, verify against PyPI before use
- Claude code generation prompt patterns — inference from general LLM practices, requires empirical validation
- Supabase webhook payload format — not directly researched, must be confirmed with mobile app team

---
*Research completed: 2026-02-23*
*Ready for roadmap: yes*
