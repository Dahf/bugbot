# Phase 1: Foundation and Ingestion - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Running Discord bot that receives Supabase webhook bug reports, displays them as rich embeds with action buttons, creates per-bug threads, persists all state in SQLite, and survives restarts. AI analysis, GitHub integration, and dashboards are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Embed presentation
- Color coding by status: color changes as bug progresses through workflow (e.g., red=new, blue=analyzing, green=resolved)
- Summary embed in main channel: show title, user, status, and severity only. Full details (console logs, device info, steps to reproduce) go in the thread
- Short hash IDs for bug identification (e.g., `#a3f2`) — not sequential
- Embed title format includes the hash ID prominently

### Webhook payload
- Existing Supabase webhook — payload structure to be provided before planning
- Single Supabase project: one webhook secret, one Discord channel
- Accept and fill gaps: store whatever fields are available, show "N/A" or "Unknown" for missing fields — never reject a bug report

### Thread behavior
- Thread per bug (not a text channel)
- Thread naming: hash + title (e.g., "#a3f2 — App crashes on login")
- First thread message: full bug details followed by a template-based summary (structured from available fields). AI summary comes in Phase 2
- Auto-archive after 30 days of inactivity (use longest Discord auto-archive option available; researcher to verify Discord API limits for the server's boost level)

### Button interactions
- Dismiss: marks as dismissed with greyed/strikethrough styling — embed stays visible in channel, data preserved in DB
- Buttons stay active after use — users can re-trigger actions if needed
- Analyze, Create Issue, and Draft Fix buttons: shown but disabled/greyed out in Phase 1 (functionality comes in Phases 2-3)
- Button clicks are role-gated: only users with a specific Discord role (e.g., "Developer") can interact with bug report buttons

### Claude's Discretion
- Emoji/icon usage in embed fields for visual distinction
- Exact embed field ordering and formatting
- Specific colors for each status state
- Template summary format in thread first message

</decisions>

<specifics>
## Specific Ideas

- User wants the hash ID approach specifically so bugs are easy to reference in conversation
- Summary embed keeps the main channel clean — thread is where the full investigation happens
- Role gating is important even for a small team — prevents accidental interactions

</specifics>

<deferred>
## Deferred Ideas

- AI-generated summary in bug threads — Phase 2 (AI Analysis)
- Multi-project webhook support — potential future enhancement

</deferred>

---

*Phase: 01-foundation-and-ingestion*
*Context gathered: 2026-02-23*
