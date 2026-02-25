# Phase 6: Developer Context via @Bot Mentions - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Developers can @mention the bot in bug threads to add context notes (thoughts, theories, pointers) that get stored and included in the code fix prompt when Draft Fix is triggered. This adds a human-in-the-loop context layer between AI analysis and code fix generation.

</domain>

<decisions>
## Implementation Decisions

### Mention-Verhalten
- Trigger: Only messages that @mention the bot in a bug thread are treated as context
- Bot confirms with emoji reaction (📝) AND a short text reply ("Context saved (N notes for this bug)")
- Empty mentions (just @Bot with no text): bot shows a brief help message instead of saving
- Timing: Context accepted any time (Claude's discretion -- likely always accept, useful for future iterations)

### Kontext-Speicherung
- Storage: New SQLite table `developer_notes` with bug_id, author, content, timestamp (consistent with existing architecture)
- No limit on number of notes per bug
- Editable and deletable: if a Discord message is edited or deleted, the stored note is updated/removed accordingly
- Attachments: Claude's discretion (likely store attachment URLs alongside text)

### Einfluss auf Code Fix
- Context flows into BOTH modes: Anthropic (in the system prompt) and Copilot (in issue body + custom_instructions)
- Developer context is presented as equal to AI analysis (neither has priority -- the AI agent weighs both)
- Prompt positioning: Claude's discretion (likely a dedicated "Developer Notes" section)
- Traceability: PR body includes a "Developer Notes" section listing all context with author and timestamp
- Draft Fix warning: if no developer context exists when Draft Fix is clicked, show a confirmation hint ("No developer context provided. Continue anyway?")

### Thread-Interaktion
- Permissions: Only users with the configured Developer role can add context
- Overview: Available via both a slash command AND a counter in the bug embed
- Bug embed: Shows a compact "📝 N Developer Notes" field (counter only, no preview)
- Slash command: Shows all collected notes for a bug with author and timestamp

### Claude's Discretion
- Exact prompt positioning of developer context relative to AI analysis
- Whether to store attachment URLs alongside text content
- Whether to accept context after Draft Fix has been triggered (recommended: always accept)
- Help message wording for empty mentions

</decisions>

<specifics>
## Specific Ideas

- Bot confirmation response format: "📝 Context saved (3 notes for this bug)" -- includes running total
- The slash command for viewing notes could reuse the existing /set-priority pattern as a reference
- Developer notes in PR body should include Discord usernames and relative timestamps

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 06-developer-context-via-bot-mentions*
*Context gathered: 2026-02-25*
