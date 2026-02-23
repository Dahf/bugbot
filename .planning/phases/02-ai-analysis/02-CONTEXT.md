# Phase 2: AI Analysis - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

On-demand Claude AI analysis of bug reports. Users trigger analysis via the Analyze button, and the bot posts a structured assessment (root cause, affected area, severity, priority score) in the bug's Discord thread. No automated/scheduled analysis — all analysis is manually triggered.

</domain>

<decisions>
## Implementation Decisions

### Analysis embed content
- Detailed breakdown for root cause: full paragraph with reasoning explaining what the AI thinks is happening, why, and what code area is affected
- Embed sections: Root cause, Severity, Affected code area, and a Suggested fix hint (short approach suggestion before Draft Fix)
- Severity displayed via color-coded embed sidebar (red=critical, orange=high, yellow=medium, green=low)
- Analysis posts as a separate embed message in the bug's thread — original bug embed stays unchanged except for status/priority updates

### Priority scoring rubric
- Standard P1-P4 scale: P1=Critical (drop everything), P2=High (this sprint), P3=Medium (soon), P4=Low (backlog)
- Weighted combination scoring: AI weighs multiple factors (severity, user impact, frequency) — no single factor dominates
- Show the reasoning: brief explanation of why it scored that way (e.g., "P2: high severity but low frequency")
- Manual override supported: team can change priority (e.g., P1→P3) via command or button — human judgment wins

### Analysis trigger flow
- On Analyze click: bot posts a visible "Analyzing bug report..." message in the bug thread that everyone can see, then edits it with the full analysis results
- One analysis per bug: Analyze button disables after analysis completes (no re-analysis)
- Original bug embed updates with status change (received → analyzing → triaged) AND priority score (P1-P4) added as a field for quick scanning
- Concurrent click protection: if someone clicks Analyze while analysis is running, ephemeral reply says "Analysis already in progress"

### Failure & cost UX
- API failure: ephemeral error message to the clicker only — no visible trace in thread, Analyze button stays active for retry
- Token usage shown as small footer text on the analysis embed (e.g., "~1.2k tokens")
- No automated budget cap — analysis is always manually triggered via button, giving the operator direct control over spend
- max_tokens set per API call to prevent runaway single requests, usage logged to console/file
- Quality feedback: team can react with thumbs-down to flag bad analysis, bot logs it for tracking AI quality over time

### Claude's Discretion
- Exact Claude API model selection and prompt engineering for analysis quality
- Analysis embed layout details (field ordering, spacing)
- How "suggested fix hint" is worded (brief vs. technical)
- Priority override UX specifics (button vs. slash command)
- Token usage format in footer

</decisions>

<specifics>
## Specific Ideas

- The "analyzing" loading message should be posted in the thread and then edited in-place with the final analysis results (no separate loading + results messages)
- Priority badge on the original bug embed enables quick scanning of the channel without opening each thread
- Thumbs-down reaction tracking is for long-term quality monitoring, not immediate action

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-ai-analysis*
*Context gathered: 2026-02-23*
