# Roadmap: PreserveFood Discord Bot

## Overview

This roadmap delivers an AI-powered Discord bot that transforms Supabase bug report webhooks into an organized, AI-assisted development workflow. The journey follows a strict dependency chain: first establish a running bot that receives and displays bug reports with persistent state (Foundation), then add Claude AI analysis and priority scoring (AI Analysis), then wire up GitHub issue creation and AI-drafted pull requests (GitHub Integration), and finally layer on smart deduplication, the bug dashboard, and release notes (Intelligence and Dashboard). Each phase delivers standalone value -- a Phase 1 bot is a useful webhook-to-Discord relay, a Phase 2 bot saves meaningful triage time, a Phase 3 bot accelerates the fix cycle, and Phase 4 adds intelligence on top of a proven system.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation and Ingestion** - Running bot that receives webhook bug reports, displays them as rich embeds with action buttons, persists state in SQLite, and survives restarts (completed 2026-02-23)
- [x] **Phase 2: AI Analysis** - Claude AI analyzes bug reports on demand, identifies root cause and severity, auto-scores priority, and posts results to per-bug threads (completed 2026-02-24)
- [ ] **Phase 3: GitHub Integration** - Create GitHub issues from analyzed bugs, trigger AI-drafted code fixes, and open pull requests with full context linking back to Discord
- [ ] **Phase 4: Intelligence and Dashboard** - Smart deduplication of similar bugs, persistent bug dashboard embed, team assignment, and auto-generated release notes

## Phase Details

### Phase 1: Foundation and Ingestion
**Goal**: Users can send bug reports via Supabase webhook and see them appear in Discord as organized, interactive embeds with per-bug threads -- and the bot remembers everything across restarts
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, FOUND-07, FOUND-08
**Success Criteria** (what must be TRUE):
  1. A Supabase webhook POST to the bot's endpoint results in a formatted bug report embed appearing in the configured Discord channel within seconds, with the webhook validated by shared secret
  2. Each bug report embed has working Analyze, Create Issue, Draft Fix, and Dismiss buttons that respond to clicks (even if most actions are placeholder/unimplemented)
  3. A Discord thread is automatically created for each bug report, providing a dedicated space for dev discussion
  4. After the bot is restarted, all previously posted bug reports still have functional buttons and all bug data is intact in SQLite
  5. Each bug displays a tracked status (received, analyzing, triaged, issue_created, fix_drafted, resolved) that updates as the bug progresses through the workflow
**Plans:** 2/2 plans complete

Plans:
- [x] 01-01-PLAN.md -- Project foundation: config, database schema, bug model, utility functions
- [x] 01-02-PLAN.md -- Webhook ingestion, Discord embeds/threads/buttons, dismiss handler, persistent interactions

### Phase 2: AI Analysis
**Goal**: Users can trigger AI analysis on any bug report and get back a structured assessment of root cause, affected area, severity, and priority -- all posted directly in the bug's thread
**Depends on**: Phase 1
**Requirements**: AI-01, AI-02, AI-03, AI-04, AI-07
**Success Criteria** (what must be TRUE):
  1. Clicking the Analyze button on a bug report triggers Claude AI analysis and posts a structured embed (root cause, affected code area, severity) in the bug's Discord thread within a reasonable time
  2. Each analyzed bug receives an auto-calculated priority score (P1-P4) based on crash type, user impact, and frequency, visible in the bug embed
  3. The bot handles AI API failures gracefully -- if Claude is unavailable, the raw bug report remains visible and the user can retry analysis later
  4. AI token usage is budgeted (max_tokens set per call) and logged, preventing runaway API costs
**Plans:** 2/2 plans complete

Plans:
- [x] 02-01-PLAN.md -- AI analysis service, database schema extensions, config, and embed builders
- [x] 02-02-PLAN.md -- Discord integration: Analyze button callback, AI cog, reaction tracking, priority override

### Phase 3: GitHub Integration
**Goal**: Users can go from an analyzed bug report to a GitHub issue with one button click, and from there to an AI-drafted pull request with another -- closing the loop from report to reviewable code change
**Depends on**: Phase 2
**Requirements**: GH-01, GH-02, GH-03, GH-04, GH-05, GH-06, GH-07, GH-08, GH-09, GH-10
**Success Criteria** (what must be TRUE):
  1. Clicking Create Issue on a bug report creates a well-structured GitHub issue in the private repo with description, device info, analysis results, and a link back to the Discord thread
  2. Clicking Draft Fix triggers AI code generation that reads relevant source files from the repo, creates a feature branch, commits the fix, and opens a pull request -- all without human intervention beyond the button click
  3. The PR description includes bug context, AI analysis summary, and a link to the Discord thread for reviewers
  4. The bot never commits to the default branch (main/master) under any circumstances, and branch names follow a consistent convention
  5. GitHub API rate limits are handled with retry and backoff, preventing partial workflows (no orphaned branches or half-created issues)
**Plans:** 4 plans

Plans:
- [x] 03-01-PLAN.md -- GitHub service foundation: config, database schema, App auth service, markdown templates
- [x] 03-02-PLAN.md -- /init slash command setup and Create Issue button with labels and embed updates
- [x] 03-03-PLAN.md -- Draft Fix button (branch + PR scaffold) and GitHub webhook event handlers with auto-resolve
- [ ] 03-04-PLAN.md -- Gap closure: source file reading, context commit, and enriched PR body for Draft Fix

### Phase 4: Intelligence and Dashboard
**Goal**: The bot becomes a team-ready bug management tool with smart deduplication, a persistent priority-sorted dashboard, team assignments, and auto-generated release notes
**Depends on**: Phase 3
**Requirements**: AI-05, AI-06, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05
**Success Criteria** (what must be TRUE):
  1. When a new bug report arrives that is similar to an existing one, the bot detects the potential duplicate and presents a human confirmation prompt rather than auto-dismissing -- grouping confirmed duplicates together
  2. A persistent bug dashboard embed in a designated channel shows all open bugs sorted by priority, with each bug's status, assignee, and linked GitHub issue/PR visible at a glance
  3. Users can assign bugs to team members via Discord, and assignments are reflected in the dashboard and bug embeds
  4. When PRs are merged for a given app version, the bot can auto-generate release notes summarizing the fixes included
  5. The dashboard updates automatically when any bug's status changes, without manual refresh
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Ingestion | 2/2 | Complete   | 2026-02-23 |
| 2. AI Analysis | 2/2 | Complete | 2026-02-24 |
| 3. GitHub Integration | 3/4 | In Progress | - |
| 4. Intelligence and Dashboard | 0/2 | Not started | - |

### Phase 5: AI Code Fix — Agentic multi-step code generation in Draft Fix Flow

**Goal:** The Draft Fix button produces real AI-generated code fixes through a multi-step agentic loop with quality validation (lint, self-review, CI), instead of scaffolding empty PRs
**Depends on:** Phase 3
**Requirements:** GH-04, GH-05, GH-06
**Plans:** 3/3 plans complete

Plans:
- [ ] 05-01-PLAN.md — GitHub service extensions (atomic commit, CI polling, install token) + config
- [ ] 05-02-PLAN.md — CodeFixService: agentic loop with clone, tool use, quality gates, iteration
- [ ] 05-03-PLAN.md — Integration: rewrite Draft Fix button, progress messages, completion embed, PR templates

### Phase 6: Developer Context via @Bot Mentions

**Goal:** Developers can @mention the bot in bug threads to add context notes that get stored, displayed in bug embeds, and injected into AI code fix prompts and PR bodies -- adding a human-in-the-loop context layer between analysis and code generation
**Depends on:** Phase 5
**Requirements:** DEV-01, DEV-02, DEV-03, DEV-04, DEV-05, DEV-06, DEV-07, DEV-08
**Plans:** 2/2 plans complete

Plans:
- [ ] 06-01-PLAN.md -- Data layer, DeveloperNotesCog (on_message, edit/delete, /view-notes), bot wiring, embed counter
- [ ] 06-02-PLAN.md -- Fix service prompt injection, PR body templates, Draft Fix no-context warning, human verification
