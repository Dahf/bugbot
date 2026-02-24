# Requirements: PreserveFood Discord Bot

**Defined:** 2026-02-23
**Core Value:** Bug reports that arrive in Discord get triaged, tracked, and fixed with minimal manual effort

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Bot Foundation

- [x] **FOUND-01**: Bot receives bug reports from Supabase webhook with secret validation
- [x] **FOUND-02**: Bot displays bug reports as rich Discord embeds (description, user, device, time, console logs)
- [x] **FOUND-03**: Bot auto-creates a Discord thread for each bug report for dev discussion
- [x] **FOUND-04**: Bot presents action buttons on each report (Analyze, Create Issue, Draft Fix, Dismiss)
- [x] **FOUND-05**: Bot persists all bug data and state in SQLite (survives restarts)
- [x] **FOUND-06**: Button interactions remain functional after bot restarts (persistent views)
- [x] **FOUND-07**: Each bug has a tracked status (received → analyzing → triaged → issue_created → fix_drafted → resolved)
- [x] **FOUND-08**: Bot handles webhook delivery failures gracefully (store-then-process pattern)

### AI Analysis

- [x] **AI-01**: User can trigger Claude AI analysis of a bug report via button
- [x] **AI-02**: AI analysis identifies root cause, affected code area, and severity
- [x] **AI-03**: AI analysis results are posted as an embed in the bug's Discord thread
- [x] **AI-04**: Bot auto-scores bug priority (P1-P4) based on crash type, user impact, and frequency
- [ ] **AI-05**: Bot detects duplicate bug reports and groups them (smart deduplication)
- [ ] **AI-06**: Deduplication shows human confirmation for uncertain matches (not auto-dismiss)
- [x] **AI-07**: AI analysis handles token budgeting (max_tokens set, usage logged)

### GitHub Integration

- [x] **GH-01**: User can create a GitHub issue from a bug report via button
- [x] **GH-02**: GitHub issue includes structured details (description, steps, device info, analysis results)
- [x] **GH-03**: GitHub issue links back to the Discord thread
- [ ] **GH-04**: User can trigger AI-drafted code fix via button
- [ ] **GH-05**: AI code fix uses repository context (reads relevant source files)
- [ ] **GH-06**: Bot creates a feature branch, commits the fix, and opens a PR automatically
- [ ] **GH-07**: PR description includes bug context, analysis, and link to Discord thread
- [ ] **GH-08**: Bot never commits to the default branch (main/master)
- [x] **GH-09**: Bot handles GitHub API rate limits with retry and backoff
- [ ] **GH-10**: Bot cleans up merged/stale branches

### Dashboard & Reporting

- [ ] **DASH-01**: Bot displays a persistent bug dashboard embed showing open bugs sorted by priority
- [ ] **DASH-02**: Dashboard shows bug status, assignee, and linked GitHub issue/PR
- [ ] **DASH-03**: User can assign bugs to team members via Discord
- [ ] **DASH-04**: Bot auto-generates release notes from merged PRs for each app version
- [ ] **DASH-05**: Dashboard updates automatically when bug status changes

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Support

- **SUP-01**: User-facing support threads where app users can provide more info
- **SUP-02**: Auto-reply to users when their reported bug is fixed
- **SUP-03**: Thread summary posted when a bug is resolved

### Advanced Intelligence

- **INTL-01**: Trend detection across bug reports (recurring patterns)
- **INTL-02**: Predictive analysis (suggest areas likely to have bugs based on PR changes)
- **INTL-03**: Natural language commands for querying bug status

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-merge of AI-generated PRs | Human always reviews and merges -- safety boundary |
| Web dashboard | Discord-first; a web UI adds infrastructure complexity without matching the workflow |
| Real-time crash monitoring (Sentry-style) | This processes reports, not live telemetry |
| Mobile app changes to bug reporting | Use existing Supabase webhook as-is |
| Complex RBAC / permissions system | Simple assignment is sufficient for a small team |
| Full codebase RAG indexing | Targeted file reading is sufficient; RAG adds complexity and cost |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Complete |
| FOUND-02 | Phase 1 | Complete |
| FOUND-03 | Phase 1 | Complete |
| FOUND-04 | Phase 1 | Complete |
| FOUND-05 | Phase 1 | Complete |
| FOUND-06 | Phase 1 | Complete |
| FOUND-07 | Phase 1 | Complete |
| FOUND-08 | Phase 1 | Complete |
| AI-01 | Phase 2 | Complete |
| AI-02 | Phase 2 | Complete |
| AI-03 | Phase 2 | Complete |
| AI-04 | Phase 2 | Complete |
| AI-05 | Phase 4 | Pending |
| AI-06 | Phase 4 | Pending |
| AI-07 | Phase 2 | Complete |
| GH-01 | Phase 3 | Complete |
| GH-02 | Phase 3 | Complete |
| GH-03 | Phase 3 | Complete |
| GH-04 | Phase 3 | Pending |
| GH-05 | Phase 3 | Pending |
| GH-06 | Phase 3 | Pending |
| GH-07 | Phase 3 | Pending |
| GH-08 | Phase 3 | Pending |
| GH-09 | Phase 3 | Complete |
| GH-10 | Phase 3 | Pending |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 4 | Pending |
| DASH-04 | Phase 4 | Pending |
| DASH-05 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0

---
*Requirements defined: 2026-02-23*
*Last updated: 2026-02-23 after roadmap creation*
