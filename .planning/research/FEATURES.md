# Feature Landscape

**Domain:** AI-powered bug triage Discord bot with GitHub automation
**Researched:** 2026-02-23
**Confidence:** MEDIUM (based on training data for discord.py, GitHub API, AI triage patterns; no live verification available)

## Table Stakes

Features users (the solo dev and future team members) expect. Missing = the bot feels broken or pointless.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Webhook ingestion and parsing | The entire input pipeline. Without it, nothing works. | Low | Accept POST from Supabase edge function, validate payload schema, extract structured fields (description, user ID, device info, console logs). Must handle malformed payloads gracefully. |
| Rich embed display of bug reports | Discord users expect formatted, scannable messages, not raw JSON dumps. | Low | Embed with severity color-coding, device info, truncated logs, timestamp. This is the "face" of every report. |
| Button-based actions on reports | Project explicitly chose buttons over slash commands. Users expect clickable workflow, not typing commands. | Medium | Minimum: Create Issue, Analyze, Dismiss. Buttons must be responsive (<3s acknowledged) even if the AI work takes longer. Use deferred responses. |
| AI-powered bug analysis | The core value prop. Without AI analysis, this is just a webhook relay. | Medium | Claude API call with structured prompt: identify root cause hypothesis, affected code area, severity assessment, reproduction likelihood. Return structured result, not freeform prose. |
| GitHub issue creation from Discord | The primary output action. Bug report in Discord must become a trackable GitHub issue. | Medium | Create issue via GitHub API with structured title, body (markdown), labels (severity, area), and link back to Discord thread. Must handle auth and private repos. |
| Per-ticket Discord threads | Reports need isolated discussion space. Cluttering a single channel is unusable beyond 5 open bugs. | Low | Auto-create thread from report message. All subsequent actions, analysis results, and discussion happen in the thread. Thread naming convention matters (e.g., "BUG-042: Crash on save"). |
| Basic error handling and resilience | Bot must not crash on bad input, API failures, or rate limits. | Medium | Retry logic for GitHub/Claude API calls, graceful degradation messages ("Analysis unavailable, try again"), Discord rate limit handling. A bot that goes silent on errors is worse than no bot. |
| Persistent state for bug tracking | Must survive restarts. Users expect "the bot remembers." | Medium | Store report-to-issue mappings, status, thread IDs. SQLite or a simple DB. Without persistence, every restart orphans all active bugs. |
| Status tracking per bug | Users need to know: is this open, being analyzed, has an issue, has a PR? | Low | State machine per bug: received -> analyzing -> triaged -> issue_created -> fix_drafted -> pr_opened -> resolved. Display current status in embed/thread. |
| Configuration via environment/config file | Webhook secret, Discord token, GitHub token, Claude API key, channel IDs. | Low | Standard .env or config.yaml. Not a "feature" users see, but missing it = hardcoded secrets = non-starter. |

## Differentiators

Features that make this bot genuinely valuable beyond a simple webhook relay. Not expected, but this is where the "AI-powered" promise delivers.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Smart deduplication | Prevents the same crash from creating 5 separate issues. Saves massive triage time, especially as user base grows. | High | Compare incoming report against recent reports using AI semantic similarity (not just string matching). Console log patterns, error messages, and affected areas should all factor in. Must handle "similar but different" cases gracefully -- suggest potential duplicate, don't auto-dismiss. |
| Priority scoring | Automated severity assessment means the dev always works on what matters most. | Medium | Score based on: crash vs. cosmetic, number of affected users (dedupe count), feature area criticality (purchases > UI polish), device coverage. Display as P1-P4 with clear rationale. |
| AI-drafted code fixes | The leap from "triage tool" to "fix accelerator." This is the killer feature. | High | Claude analyzes console logs + codebase context to propose a fix. Requires: repo access (clone or API), relevant file identification, diff generation. Output: branch name, changed files, explanation of fix. Must be framed as "draft" -- human reviews everything. |
| Automated PR creation | Completes the loop from report to reviewable code change. | High | Create branch, commit AI-generated changes, open PR with structured description linking back to Discord thread and GitHub issue. PR description must include: what the bug was, what the fix does, what to test. |
| Bug dashboard embed | At-a-glance view of all open bugs, their status, and priority. | Medium | Persistent embed message (updated in-place) showing open bugs sorted by priority. Include: bug ID, title, status, assignee, age. Refresh on state changes. Avoids the "scroll through 50 threads" problem. |
| Auto-generated release notes | Turns merged PRs into human-readable changelog. Saves the "what shipped?" overhead. | Medium | Watch for PR merge events (GitHub webhook or polling). Aggregate merged bug fixes into categorized release notes. Post to a release channel or update a pinned message. |
| Codebase context injection for AI | The difference between generic AI advice and actually useful analysis. | High | Give Claude access to relevant source files, project structure, recent changes. This transforms analysis from "this looks like a null reference" to "the crash is likely in FoodItem.tsx line 42 where preservationDate can be undefined after the migration in PR #87." |
| Assignment and ownership | Multi-user support. When collaborators join, they need to claim bugs. | Low | Assign button, mention in thread, track assignee in state. Simple but essential for team scaling. |
| Thread summary on resolution | When a bug is resolved, post a summary: what it was, what fixed it, how long it took. | Low | Useful for retrospectives and building institutional knowledge. AI can generate from thread history. |

## Anti-Features

Features to explicitly NOT build. These are tempting but wrong for this project.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-merge of AI PRs | PROJECT.md explicitly scopes this out. AI-generated code must always be human-reviewed. Auto-merge is dangerous for a production app with in-app purchases. | Always require manual review and merge. Bot can remind about open PRs but never merge. |
| Real-time crash monitoring (Sentry-style) | This processes structured reports, not live telemetry. Building crash monitoring is a separate product. Scope creep into APM territory. | Integrate with existing Supabase webhook. If Sentry is needed later, it is a separate tool that can feed into this bot. |
| User-facing support threads | PROJECT.md scopes this as internal dev only. Support adds moderation, privacy, and UX complexity that distracts from the core triage mission. | Keep bot in a private dev channel/server. User-facing support is a separate concern. |
| Slash command interface (as primary) | Project chose buttons for discoverability and speed. Slash commands add maintenance burden and split the interaction model. | Buttons as primary. A few slash commands for admin (e.g., /config, /status) are fine, but the triage workflow should be button-driven. |
| Modifying the mobile app's bug reporting | The Supabase webhook is the contract boundary. Changing the upstream reporting format couples the bot to the app's release cycle. | Treat the webhook payload as a stable API. Parse what arrives. If richer data is needed, request it as a separate app change. |
| Complex RBAC/permissions system | Overkill for solo-to-small-team. Discord's built-in roles handle basic access control. Building a custom permission layer wastes time. | Use Discord role checks (e.g., "Developer" role can use buttons). Simple allowlist in config if needed. |
| Natural language command parsing | "Hey bot, what bugs are open?" is fun but unreliable and expensive (AI call per message). Buttons and structured commands are more reliable. | Buttons for actions, slash commands for queries. Do not monitor all messages for intent. |
| Web dashboard | A Discord bot should keep its UI in Discord. Building a web frontend splits attention, adds hosting/auth complexity, and duplicates state. | The dashboard embed in Discord IS the dashboard. If a web view is ever needed, it is a separate project. |
| Automatic codebase indexing/RAG | Full repo indexing with vector embeddings is complex infrastructure. For a small codebase with low report volume, it is overkill. | Pass relevant files to Claude directly based on error messages and file paths in console logs. Simple grep/search over cloned repo is sufficient at this scale. |

## Feature Dependencies

```
Webhook Ingestion
  --> Rich Embed Display
    --> Button-Based Actions
      --> Per-Ticket Threads (created on first action)
      --> AI Bug Analysis (triggered by Analyze button)
        --> Priority Scoring (uses analysis output)
        --> Smart Deduplication (compares analysis results)
      --> GitHub Issue Creation (triggered by Create Issue button)
        --> Assignment/Ownership (assign after issue exists)
      --> AI-Drafted Code Fix (triggered by Draft Fix button)
        --> Codebase Context Injection (required for useful fixes)
        --> Automated PR Creation (packages fix into PR)
          --> Auto-Generated Release Notes (watches for PR merges)

Persistent State (required by ALL stateful features)
  --> Status Tracking
  --> Bug Dashboard Embed
  --> Smart Deduplication (needs history)

Configuration/Environment
  --> All features (tokens, secrets, channel IDs)

Error Handling/Resilience
  --> All API-calling features
```

Key dependency chains:
- **Cannot build AI fixes without codebase context** -- without repo access, Claude produces generic advice, not actionable diffs.
- **Cannot build deduplication without analysis** -- comparing raw text is brittle; semantic comparison needs structured analysis output.
- **Cannot build release notes without PR creation** -- release notes aggregate from merged PRs.
- **Dashboard depends on persistent state** -- no state = nothing to display.

## MVP Recommendation

### Phase 1: The Report-to-Issue Pipeline (table stakes)

Prioritize in this order:

1. **Webhook ingestion and parsing** -- the input
2. **Rich embed display** -- make reports readable
3. **Per-ticket threads** -- isolate discussions
4. **Button-based actions** -- the interaction model
5. **Persistent state** -- survive restarts
6. **Status tracking** -- know where each bug stands
7. **AI bug analysis** -- the first AI value
8. **GitHub issue creation** -- the first automation value

This gets you from "bug report arrives" to "GitHub issue exists with AI analysis" with a clear, button-driven workflow.

### Phase 2: Intelligence Layer (differentiators)

9. **Priority scoring** -- builds on analysis, low incremental effort
10. **Smart deduplication** -- prevents duplicate work, high value for growing user base
11. **Bug dashboard embed** -- at-a-glance status view

### Phase 3: Fix Acceleration (the killer features)

12. **Codebase context injection** -- prerequisite for good fixes
13. **AI-drafted code fixes** -- the big differentiator
14. **Automated PR creation** -- completes the loop
15. **Assignment/ownership** -- ready for team scaling

### Phase 4: Polish

16. **Auto-generated release notes** -- nice-to-have, depends on PR workflow being stable
17. **Thread summary on resolution** -- retrospective value

### Defer Indefinitely

- Web dashboard, natural language commands, complex RBAC, auto-merge, codebase RAG indexing

**Rationale:** Phase 1 delivers immediate value (organized bug reports with AI analysis and GitHub tracking). Each subsequent phase builds on proven foundations. The high-complexity AI features (fixes, PRs) come after the data pipeline and state management are solid, because debugging AI code generation on top of a buggy bot is miserable.

## Complexity Budget

| Complexity | Count | Features |
|------------|-------|----------|
| Low | 7 | Webhook ingestion, embed display, threads, status tracking, config, assignment, thread summary |
| Medium | 6 | Button actions, AI analysis, error handling, persistent state, priority scoring, dashboard, release notes |
| High | 4 | Smart deduplication, AI code fixes, PR creation, codebase context injection |

The high-complexity features are all in Phase 3. This is intentional -- they depend on stable foundations and carry the most risk. If they prove too complex, the bot is still fully useful through Phase 2.

## Sources

- Project context from `.planning/PROJECT.md`
- Discord.py documentation patterns (training data, MEDIUM confidence)
- GitHub REST API capabilities for issue/PR creation (training data, HIGH confidence -- well-established API)
- Claude API patterns for structured analysis (training data, MEDIUM confidence)
- Discord bot UX patterns: buttons, threads, embeds (training data, MEDIUM confidence)
- Bug triage workflow patterns from issue trackers (training data, MEDIUM confidence)

**Note:** Live verification of discord.py v2.x button/thread APIs, current Claude API structured output features, and GitHub API rate limits should be performed during phase-specific research. These are well-established technologies unlikely to have changed fundamentally, but version-specific details matter for implementation.
