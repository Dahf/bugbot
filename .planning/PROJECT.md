# PreserveFood Discord Bot

## What This Is

An AI-powered Discord bot that automates the bug triage and fix pipeline for a React Native food preservation app. Bug reports arrive via Supabase edge function webhooks, get analyzed by Claude AI, and flow through a button-driven workflow that creates GitHub issues, drafts code fixes, opens pull requests, and tracks everything in per-ticket Discord threads. Built for a solo dev scaling to a small team.

## Core Value

Bug reports that arrive in Discord get triaged, tracked, and fixed with minimal manual effort — turning a chaotic stream of reports into an organized, AI-assisted development workflow.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Bot receives and parses bug reports from Supabase webhook
- [ ] Claude AI analyzes bug reports (root cause, affected area, severity)
- [ ] Smart deduplication — detects when multiple reports describe the same bug
- [ ] Priority scoring based on crash severity, user impact, frequency
- [ ] Button-based interaction on each report (Create Issue, Analyze, Draft Fix, Dismiss)
- [ ] Per-ticket Discord threads for internal dev discussion
- [ ] GitHub issue creation from Discord with structured details
- [ ] AI-drafted code fixes with branch creation and pull requests
- [ ] Bug dashboard embed showing open bugs, status, assignments
- [ ] Auto-generated release notes from merged PRs
- [ ] Multi-user support — assignments, permissions, team visibility

### Out of Scope

- User-facing support threads — internal dev only for now
- Mobile app changes to the bug reporting system — use existing Supabase webhook as-is
- Real-time crash monitoring (Sentry-style) — this processes reports, not live telemetry
- Automatic merging of AI-generated PRs — human always reviews and merges

## Context

- **App**: React Native food preservation app with in-app purchases, iOS (likely Android too)
- **Bug reports**: Structured format with description, user ID, device info, timestamp, console logs (last 15-24 lines)
- **Webhook source**: Supabase edge function currently sends to Discord channel; will also send to bot's own listener
- **Code hosting**: Private GitHub repository
- **Current volume**: A few reports per week — low volume but automation still high-value for solo dev
- **Team trajectory**: Solo now, expecting collaborators soon

## Constraints

- **Language**: Python — chosen for strong Discord.py and AI library ecosystem
- **Hosting**: Self-hosted Docker container on existing VPS
- **AI Provider**: Anthropic Claude API for analysis and code generation
- **GitHub**: Must work with private repositories (authenticated API access)
- **Discord**: Bot must handle concurrent interactions without blocking

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over TypeScript | Strong discord.py ecosystem, good AI library support | — Pending |
| Button-based interaction | More discoverable than slash commands, faster than reactions | — Pending |
| Claude for AI | User preference, strong code analysis capabilities | — Pending |
| Own webhook listener + Discord | Full control over report data, not limited to Discord message parsing | — Pending |
| Docker deployment | Matches existing VPS infrastructure | — Pending |

---
*Last updated: 2026-02-23 after initialization*
