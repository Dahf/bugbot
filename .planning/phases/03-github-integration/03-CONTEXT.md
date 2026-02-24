# Phase 3: GitHub Integration - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Go from an analyzed bug report to a GitHub issue (one button click) and from there to an AI-drafted pull request (another click). Full bidirectional linking between Discord and GitHub. Includes repo connection setup via Discord command and GitHub App. Deduplication, dashboard, and team assignment are Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Repo connection & authentication
- GitHub App installation for fine-grained permissions (not personal access tokens)
- Discord `/init` slash command walks user through connecting a repo
- `/init` provides the GitHub App install link, then enters a waiting/polling loop until installation is detected
- After install, bot auto-detects which repos the App was installed on and lets user pick if multiple
- Single repo per Discord server (not per-channel)

### Issue creation
- Issue body includes ALL context: bug description + steps, device/environment info, AI analysis results, and Discord thread link
- Auto-apply labels from AI analysis (priority labels like P1-critical, area labels like area:auth)
- Bot auto-creates missing labels (with colors) if they don't exist in the repo
- Single configured repo per server (set via /init)

### AI code fix scope
- Hybrid approach: bot creates branch + PR scaffold, external tool (GitHub Copilot/BugBot) handles actual code generation
- If external tool doesn't produce a fix, leave PR as a shell with full bug context (no Claude fallback)
- No file/directory guardrails — external tool can touch any files it determines are relevant

### Branch & PR conventions
- Branch naming: `bot/bug-{id}-{short-desc}` (e.g., `bot/bug-42-login-crash`)
- Never commit to default branch (main/master) — always feature branches
- PR description includes: bug summary, AI analysis, Discord thread link, and `Closes #{issue}` to auto-close on merge
- If branch already exists for a bug (re-trigger), block and notify user with link to existing branch/PR
- Auto-delete branch on PR merge

### Discord feedback loop
- When issue is created: update original bug embed (status + issue link) AND post message in bug thread
- When PR is opened: update embed status to 'fix_drafted' AND post PR link in thread
- Full GitHub webhook tracking: listen for PR status changes (merged, closed, review requested) and update Discord
- Auto-resolve on merge: when PR is merged, bug status automatically becomes 'resolved' and embed updates

### Claude's Discretion
- Exact GitHub App permissions scope
- GitHub webhook event filtering (which events to subscribe to)
- Rate limit retry/backoff strategy (GH-09)
- Issue template formatting details
- Label color scheme

</decisions>

<specifics>
## Specific Ideas

- User mentioned "BugBot by GitHub" as inspiration for the code fix flow — hybrid model where bot scaffolds and external tool fills in code
- The `/init` command should feel polished: show install link, wait for completion, auto-detect repo — not a raw token-paste experience
- Everything links back: Discord thread links in GitHub issues/PRs, GitHub links in Discord embeds/threads

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-github-integration*
*Context gathered: 2026-02-24*
