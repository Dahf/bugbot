# Phase 2: AI Analysis - Research

**Researched:** 2026-02-23
**Domain:** LLM-powered bug report analysis via Anthropic Claude API + Discord bot integration
**Confidence:** HIGH

## Summary

Phase 2 adds on-demand Claude AI analysis to bug reports. When a user clicks the existing "Analyze" button (already wired as a disabled DynamicItem in Phase 1), the bot calls the Anthropic Messages API with the bug's details, posts a "loading" message in the bug's thread, then edits it in-place with a structured analysis embed (root cause, affected code area, severity, suggested fix hint, and a P1-P4 priority score). The original bug embed in the channel also gets updated with the new status and priority field.

The Anthropic Python SDK (`anthropic`) provides a fully async client (`AsyncAnthropic`) that integrates naturally with the bot's existing asyncio architecture. Token usage is returned in every API response via `message.usage` (input_tokens + output_tokens), and `max_tokens` caps output per call. The SDK has built-in retry with exponential backoff for transient errors (429, 5xx), and a clear exception hierarchy for error handling.

**Primary recommendation:** Use `anthropic.AsyncAnthropic` with `claude-haiku-4-5-20251001` as the default model (fastest, cheapest at $1/$5 per MTok) and `max_tokens=1024` per analysis call. The analysis prompt should instruct Claude to return JSON with structured fields. Use a new `src/services/ai_analysis.py` module to encapsulate all AI logic, keeping it separate from Discord UI concerns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Detailed breakdown for root cause: full paragraph with reasoning explaining what the AI thinks is happening, why, and what code area is affected
- Embed sections: Root cause, Severity, Affected code area, and a Suggested fix hint (short approach suggestion before Draft Fix)
- Severity displayed via color-coded embed sidebar (red=critical, orange=high, yellow=medium, green=low)
- Analysis posts as a separate embed message in the bug's thread -- original bug embed stays unchanged except for status/priority updates
- Standard P1-P4 scale: P1=Critical (drop everything), P2=High (this sprint), P3=Medium (soon), P4=Low (backlog)
- Weighted combination scoring: AI weighs multiple factors (severity, user impact, frequency) -- no single factor dominates
- Show the reasoning: brief explanation of why it scored that way (e.g., "P2: high severity but low frequency")
- Manual override supported: team can change priority (e.g., P1->P3) via command or button -- human judgment wins
- On Analyze click: bot posts a visible "Analyzing bug report..." message in the bug thread that everyone can see, then edits it with the full analysis results
- One analysis per bug: Analyze button disables after analysis completes (no re-analysis)
- Original bug embed updates with status change (received -> analyzing -> triaged) AND priority score (P1-P4) added as a field for quick scanning
- Concurrent click protection: if someone clicks Analyze while analysis is running, ephemeral reply says "Analysis already in progress"
- API failure: ephemeral error message to the clicker only -- no visible trace in thread, Analyze button stays active for retry
- Token usage shown as small footer text on the analysis embed (e.g., "~1.2k tokens")
- No automated budget cap -- analysis is always manually triggered via button, giving the operator direct control over spend
- max_tokens set per API call to prevent runaway single requests, usage logged to console/file
- Quality feedback: team can react with thumbs-down to flag bad analysis, bot logs it for tracking AI quality over time
- The "analyzing" loading message should be posted in the thread and then edited in-place with the final analysis results (no separate loading + results messages)
- Priority badge on the original bug embed enables quick scanning of the channel without opening each thread
- Thumbs-down reaction tracking is for long-term quality monitoring, not immediate action

### Claude's Discretion
- Exact Claude API model selection and prompt engineering for analysis quality
- Analysis embed layout details (field ordering, spacing)
- How "suggested fix hint" is worded (brief vs. technical)
- Priority override UX specifics (button vs. slash command)
- Token usage format in footer

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AI-01 | User can trigger Claude AI analysis of a bug report via button | Anthropic AsyncAnthropic SDK + existing DynamicItem button callback in `bug_buttons.py` -- enable the "analyze" action, call AI service, post results |
| AI-02 | AI analysis identifies root cause, affected code area, and severity | System prompt engineering with structured JSON output; Claude extracts these fields from bug description, device info, console logs |
| AI-03 | AI analysis results are posted as an embed in the bug's Discord thread | discord.py thread.send() for loading message, then message.edit() with analysis embed -- verified patterns from Context7 |
| AI-04 | Bot auto-scores bug priority (P1-P4) based on crash type, user impact, and frequency | Include priority scoring rubric in the system prompt; Claude returns priority + reasoning as part of structured JSON response |
| AI-07 | AI analysis handles token budgeting (max_tokens set, usage logged) | `max_tokens` parameter on messages.create(), `message.usage.input_tokens` + `message.usage.output_tokens` for logging |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | >=0.80.0,<1.0.0 | Anthropic Claude API client | Official SDK from Anthropic; HIGH reputation, async support, built-in retry, typed responses |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| discord.py | >=2.6.0,<3.0.0 | Discord bot framework | Already in use (Phase 1); embeds, thread messaging, button interactions |
| aiosqlite | >=0.22.0,<1.0.0 | Async SQLite | Already in use (Phase 1); stores analysis results, priority, token usage |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| anthropic SDK | litellm | Multi-provider abstraction adds complexity; not needed since we're Anthropic-only |
| anthropic SDK | Raw HTTP via aiohttp | Lose typed responses, auto-retry, error hierarchy; already have aiohttp in project but SDK is far superior |
| claude-haiku-4-5 (default) | claude-sonnet-4-5 | 3x more expensive ($3/$15 vs $1/$5 per MTok); Haiku 4.5 is sufficient for structured bug analysis; user can override via env var |

**Installation:**
```bash
pip install "anthropic>=0.80.0,<1.0.0"
```

**Model recommendation:** `claude-haiku-4-5-20251001` (alias: `claude-haiku-4-5`)
- Input: $1/MTok, Output: $5/MTok
- 200K context window, 64K max output
- Fastest model -- good for interactive Discord use where response time matters
- Configurable via `ANTHROPIC_MODEL` env var so operators can upgrade to Sonnet/Opus if desired

## Architecture Patterns

### Recommended Project Structure
```
src/
├── bot.py                  # (exists) Bot setup, DynamicItem registration
├── config.py               # (exists) Add ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AI_MAX_TOKENS
├── cogs/
│   ├── webhook.py          # (exists) Webhook ingestion
│   ├── bug_reports.py      # (exists) Queue consumer, posting
│   └── ai_analysis.py      # (NEW) Cog for AI analysis event handling, reaction tracking
├── models/
│   ├── database.py         # (exists) Add analysis columns to schema
│   └── bug.py              # (exists) Add analysis CRUD methods
├── services/
│   └── ai_analysis.py      # (NEW) Core AI logic: prompt building, API call, response parsing
├── utils/
│   ├── embeds.py           # (exists) Add analysis embed builder, update summary embed for priority
│   └── ...                 # (exists) Other utils
└── views/
    └── bug_buttons.py      # (exists) Enable analyze button, add priority override
```

### Pattern 1: Service Layer for AI Logic
**What:** Separate AI API calls and prompt engineering into `src/services/ai_analysis.py`, keeping Discord-specific code in cogs/views.
**When to use:** Always -- this is the fundamental separation for this phase.
**Example:**
```python
# src/services/ai_analysis.py
import json
import logging
from anthropic import AsyncAnthropic, APIError

logger = logging.getLogger(__name__)

class AIAnalysisService:
    """Encapsulates Claude API interactions for bug analysis."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1024):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def analyze_bug(self, bug: dict) -> dict:
        """Analyze a bug report and return structured results.

        Returns dict with keys: root_cause, affected_area, severity,
        suggested_fix, priority, priority_reasoning, usage.
        Raises anthropic.APIError subclasses on failure.
        """
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(bug)

        message = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract text content
        text = message.content[0].text

        # Parse structured JSON from response
        result = json.loads(text)

        # Attach token usage
        result["usage"] = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "total_tokens": message.usage.input_tokens + message.usage.output_tokens,
        }

        return result
```
Source: Context7 /anthropics/anthropic-sdk-python -- AsyncAnthropic, messages.create, message.usage

### Pattern 2: In-Place Loading Message Edit
**What:** Post a "loading" message in the thread, then edit it with the full analysis embed once complete.
**When to use:** On every Analyze button click that passes validation.
**Example:**
```python
# In the analyze button callback (cog or view):
async def _handle_analyze(self, interaction: discord.Interaction):
    # 1. Defer the interaction (ephemeral=False not needed, we send to thread)
    await interaction.response.defer(ephemeral=True)

    # 2. Post loading message in thread (visible to everyone)
    thread = interaction.message.thread
    loading_msg = await thread.send("Analyzing bug report... please wait.")

    try:
        # 3. Call AI service
        result = await bot.ai_service.analyze_bug(bug)

        # 4. Build analysis embed from result
        embed = build_analysis_embed(bug, result)

        # 5. Edit loading message with embed (in-place replacement)
        await loading_msg.edit(content=None, embed=embed)

    except anthropic.APIError:
        # 6. Delete loading message, send ephemeral error
        await loading_msg.delete()
        await interaction.followup.send("AI analysis failed. Try again later.", ephemeral=True)
```
Source: Context7 /rapptz/discord.py -- interaction.response.defer, thread.send, message.edit

### Pattern 3: Concurrent Click Guard via Status
**What:** Use the bug's status field in the database as a lock to prevent duplicate analysis.
**When to use:** Every Analyze button click -- check status before proceeding.
**Example:**
```python
async def _handle_analyze(self, interaction):
    bug = await bot.bug_repo.get_bug(self.bug_id)

    # Guard: already analyzing or already analyzed
    if bug["status"] in ("analyzing", "triaged", "issue_created", "fix_drafted", "resolved"):
        await interaction.response.send_message(
            "Analysis already in progress" if bug["status"] == "analyzing"
            else "This bug has already been analyzed.",
            ephemeral=True,
        )
        return

    # Atomically set status to "analyzing" before starting
    await bot.bug_repo.update_status(self.bug_id, "analyzing", str(interaction.user))
    # ... proceed with analysis
```

### Pattern 4: Structured JSON Output from Claude
**What:** Use a system prompt that instructs Claude to respond in strict JSON format with predefined fields.
**When to use:** Every analysis call -- ensures parseable, structured output.
**Example system prompt:**
```python
SYSTEM_PROMPT = """You are a senior software engineer triaging bug reports for a mobile application.

Analyze the bug report and respond with ONLY a JSON object (no markdown, no code fences) with these exact fields:

{
  "root_cause": "A detailed paragraph explaining the likely root cause, your reasoning, and what is happening technically.",
  "affected_area": "The specific code area, module, or feature most likely affected (e.g., 'Authentication module', 'Camera capture flow').",
  "severity": "One of: critical, high, medium, low",
  "suggested_fix": "A brief 1-2 sentence hint about the recommended fix approach.",
  "priority": "One of: P1, P2, P3, P4",
  "priority_reasoning": "Brief explanation of the priority score (e.g., 'P2: high severity crash but low frequency affecting <1% of users')."
}

Priority scoring rubric:
- P1 (Critical): App crashes, data loss, security vulnerabilities, or issues affecting >50% of users. Drop everything.
- P2 (High): Major feature broken, significant UX degradation, or moderate user impact. This sprint.
- P3 (Medium): Minor feature issues, cosmetic bugs with workarounds, low user impact. Soon.
- P4 (Low): Edge cases, minor polish, nice-to-haves. Backlog.

Weigh multiple factors: severity of the bug itself, estimated user impact/reach, and likely frequency of occurrence. No single factor should dominate."""
```

### Anti-Patterns to Avoid
- **Putting AI logic in the button callback:** Mixing API calls with Discord interaction handling creates untestable, hard-to-maintain code. Always use a service layer.
- **Streaming for analysis:** Streaming adds complexity (partial JSON parsing) for minimal UX benefit in this use case. A loading message + single edit is simpler and more reliable.
- **Using interaction.response.send_message for the loading message:** The interaction response is for the button clicker; the loading message should be posted to the thread as a regular message visible to everyone.
- **Relying on in-memory locks for concurrency:** Bot restarts would lose the lock. Use the database status field as the source of truth.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry with backoff | Custom retry loops for API calls | `anthropic` SDK built-in retry (default 2 retries, exponential backoff for 429/5xx) | SDK handles it correctly with jitter; configurable via `max_retries` |
| Token counting | Manual character-to-token estimation | `message.usage.input_tokens` + `message.usage.output_tokens` from API response | Exact count from the API; no estimation needed |
| JSON response parsing | Custom text extraction / regex | `json.loads()` on `message.content[0].text` with fallback handling | Claude follows JSON instructions reliably; a simple try/except covers edge cases |
| Rate limiting | Custom rate limiter | SDK auto-retries on 429 with backoff | SDK handles this transparently |

**Key insight:** The Anthropic SDK handles the hard parts (retry, rate limiting, error classification, token tracking). The implementation work is primarily in prompt engineering, Discord UX flow, and database schema updates.

## Common Pitfalls

### Pitfall 1: Not Deferring the Interaction Before Long Operations
**What goes wrong:** Discord requires interaction responses within 3 seconds. AI analysis takes 5-30 seconds. The interaction token expires, making followup impossible.
**Why it happens:** Developers forget that button clicks need an immediate response.
**How to avoid:** Always `await interaction.response.defer(ephemeral=True)` immediately in the Analyze callback. Use `interaction.followup.send()` for subsequent messages to the clicker.
**Warning signs:** "This interaction failed" errors in Discord, or silent failures.

### Pitfall 2: JSON Parsing Failures from Claude Response
**What goes wrong:** Claude occasionally wraps JSON in markdown code fences (```json ... ```) or adds explanatory text, causing `json.loads()` to fail.
**Why it happens:** LLMs sometimes deviate from instructions despite clear prompts.
**How to avoid:** Strip markdown code fences before parsing. If `json.loads()` fails, try extracting content between `{` and `}`. Log the raw response for debugging.
**Warning signs:** `json.JSONDecodeError` exceptions in logs.

### Pitfall 3: Loading Message Left Dangling on Failure
**What goes wrong:** If the AI call fails after posting the "Analyzing..." message, the loading message stays in the thread with no resolution, confusing users.
**Why it happens:** Error handling doesn't clean up the loading message.
**How to avoid:** On API failure, delete the loading message and revert the bug status from "analyzing" back to "received". Send an ephemeral error to the clicker.
**Warning signs:** Stale "Analyzing..." messages in threads with no follow-up.

### Pitfall 4: Forgetting to Update Both the Thread AND the Channel Embed
**What goes wrong:** The analysis posts in the thread but the main channel embed still shows "Received" status with no priority badge.
**Why it happens:** Only the thread message is updated; the original channel message edit is forgotten.
**How to avoid:** After successful analysis: (1) edit loading message with analysis embed, (2) update bug status to "triaged" in DB, (3) rebuild and edit the original channel embed with new status + priority field.
**Warning signs:** Channel embeds always showing "Received" even after analysis.

### Pitfall 5: Not Handling the "Bug Has No Thread" Edge Case
**What goes wrong:** If the thread failed to create in Phase 1 (thread_id is 0), the Analyze handler tries to send to a None thread and crashes.
**Why it happens:** Phase 1 stores thread_id=0 when thread creation fails but the embed still posts successfully.
**How to avoid:** Check for thread_id=0 and either create the thread on-the-fly or send an ephemeral error explaining the thread is missing.
**Warning signs:** AttributeError on NoneType when trying to send to thread.

### Pitfall 6: Anthropic API Key Not Configured
**What goes wrong:** Bot starts fine but crashes on first Analyze click because no API key is set.
**Why it happens:** ANTHROPIC_API_KEY is a Phase 2 addition -- existing deployments won't have it.
**How to avoid:** Make ANTHROPIC_API_KEY a required config if the AI cog is loaded, but don't block bot startup. The Analyze button should return a clear ephemeral error if the AI service is not configured.
**Warning signs:** `AuthenticationError` on first analysis attempt.

## Code Examples

Verified patterns from official sources:

### AsyncAnthropic Client Setup
```python
# Source: Context7 /anthropics/anthropic-sdk-python
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key="sk-ant-...")

message = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system="You are a bug triage assistant. Respond in JSON only.",
    messages=[{"role": "user", "content": "Analyze this bug: ..."}],
)

# Access response text
text = message.content[0].text  # str

# Access token usage
print(message.usage.input_tokens)   # int
print(message.usage.output_tokens)  # int
```

### Error Handling Hierarchy
```python
# Source: Context7 /anthropics/anthropic-sdk-python
import anthropic

try:
    message = await client.messages.create(...)
except anthropic.APIConnectionError as e:
    # Network/connection failure
    logger.error("Claude API connection error: %s", e.__cause__)
except anthropic.RateLimitError as e:
    # 429 -- SDK already retried and still rate limited
    logger.warning("Claude API rate limited: %s", e.response)
except anthropic.AuthenticationError as e:
    # 401 -- bad API key
    logger.error("Claude API auth failed: %s", e.message)
except anthropic.BadRequestError as e:
    # 400 -- malformed request (e.g., prompt too long)
    logger.error("Claude API bad request: %s", e.message)
except anthropic.APIStatusError as e:
    # Other 4xx/5xx
    logger.error("Claude API error %d: %s", e.status_code, e.message)
```

### Retry Configuration
```python
# Source: Context7 /anthropics/anthropic-sdk-python
# SDK defaults: 2 retries with exponential backoff for 429/5xx
# Override if needed:
client = AsyncAnthropic(
    api_key="...",
    max_retries=3,    # default is 2
    timeout=60.0,     # default is 600s; 60s is reasonable for analysis
)
```

### Discord: Editing a Thread Message with an Embed
```python
# Source: Context7 /rapptz/discord.py
# Post loading message
loading_msg = await thread.send("Analyzing bug report...")

# Build embed
embed = discord.Embed(
    title="AI Analysis",
    color=discord.Colour.blue(),
)
embed.add_field(name="Root Cause", value="...", inline=False)

# Edit in-place
await loading_msg.edit(content=None, embed=embed)
```

### Discord: Interaction Defer + Followup
```python
# Source: Context7 /rapptz/discord.py
# Must defer within 3 seconds
await interaction.response.defer(ephemeral=True)

# ... do long work ...

# Send result to user (ephemeral)
await interaction.followup.send("Analysis complete!", ephemeral=True)
```

### Building a Color-Coded Severity Embed
```python
SEVERITY_COLORS = {
    "critical": discord.Colour(0xED4245),  # Red
    "high": discord.Colour(0xE67E22),       # Orange
    "medium": discord.Colour(0xF1C40F),     # Yellow
    "low": discord.Colour(0x2ECC71),        # Green
}

def build_analysis_embed(bug: dict, analysis: dict) -> discord.Embed:
    severity = analysis["severity"]
    total_tokens = analysis["usage"]["total_tokens"]

    embed = discord.Embed(
        title=f"AI Analysis -- #{bug['hash_id']}",
        color=SEVERITY_COLORS.get(severity, discord.Colour.default()),
    )
    embed.add_field(name="Root Cause", value=analysis["root_cause"], inline=False)
    embed.add_field(name="Affected Area", value=analysis["affected_area"], inline=True)
    embed.add_field(name="Severity", value=severity.title(), inline=True)
    embed.add_field(
        name="Priority",
        value=f"**{analysis['priority']}** -- {analysis['priority_reasoning']}",
        inline=False,
    )
    embed.add_field(name="Suggested Fix", value=analysis["suggested_fix"], inline=False)

    # Token usage footer
    if total_tokens >= 1000:
        token_display = f"~{total_tokens / 1000:.1f}k tokens"
    else:
        token_display = f"~{total_tokens} tokens"
    embed.set_footer(text=f"Analysis by Claude | {token_display}")

    return embed
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `claude-3-haiku-20240307` | `claude-haiku-4-5-20251001` | Oct 2025 | Near-frontier intelligence at lowest cost; old Haiku 3 deprecated Apr 2026 |
| `anthropic` <0.30 (sync only) | `anthropic` >=0.80 (AsyncAnthropic) | 2025 | Full async/await support, typed responses, built-in retry |
| Streaming for all LLM calls | Non-streaming for structured output | Current best practice | JSON parsing is simpler with complete response; streaming only needed for long-form user-facing text |
| Manual retry with backoff | SDK built-in retry (max_retries param) | anthropic SDK >=0.20 | Automatic retry for 429/5xx with exponential backoff and jitter |

**Deprecated/outdated:**
- `claude-3-haiku-20240307`: Deprecated, retiring April 2026. Use `claude-haiku-4-5-20251001`.
- `claude-3-opus-20240229` / `claude-3-sonnet-20240229`: Fully deprecated. Use 4.x family.
- `anthropic.HUMAN_PROMPT` / `anthropic.AI_PROMPT`: Old completion API; Messages API is the current standard.

## Database Schema Changes

The existing `bugs` table needs new columns for analysis results:

```sql
-- New columns on bugs table
ALTER TABLE bugs ADD COLUMN priority TEXT;           -- P1/P2/P3/P4
ALTER TABLE bugs ADD COLUMN priority_reasoning TEXT;  -- Brief explanation
ALTER TABLE bugs ADD COLUMN ai_root_cause TEXT;       -- Full root cause paragraph
ALTER TABLE bugs ADD COLUMN ai_affected_area TEXT;    -- Affected code area
ALTER TABLE bugs ADD COLUMN ai_severity TEXT;         -- AI-assessed severity (may differ from user-reported)
ALTER TABLE bugs ADD COLUMN ai_suggested_fix TEXT;    -- Fix hint
ALTER TABLE bugs ADD COLUMN ai_tokens_used INTEGER;   -- Total tokens for this analysis
ALTER TABLE bugs ADD COLUMN analysis_message_id INTEGER; -- Discord message ID of the analysis embed in thread
ALTER TABLE bugs ADD COLUMN analyzed_at TEXT;         -- Timestamp of analysis completion
ALTER TABLE bugs ADD COLUMN analyzed_by TEXT;         -- Discord user who triggered analysis
```

For the `CREATE TABLE IF NOT EXISTS` approach (existing pattern), add these columns to the schema in `database.py`. Since SQLite does not support `ALTER TABLE ADD COLUMN IF NOT EXISTS`, handle migration by checking existing columns or use the `CREATE TABLE IF NOT EXISTS` pattern with the full schema (existing rows are preserved since the table already exists -- new columns just won't appear on old rows unless migration is explicit).

**Recommendation:** Add columns to the schema definition. For the dev/staging database, it is simplest to recreate the DB. For production continuity, add a migration function that checks and adds missing columns.

## Config Changes

```python
# New env vars for config.py
ANTHROPIC_API_KEY: str       # Required for AI analysis
ANTHROPIC_MODEL: str         # Optional, default "claude-haiku-4-5-20251001"
AI_MAX_TOKENS: int           # Optional, default 1024
```

## Open Questions

1. **JSON parsing robustness**
   - What we know: Claude generally follows JSON-only instructions well, especially with a clear system prompt
   - What's unclear: Failure rate for Haiku 4.5 specifically on strict JSON output (no markdown wrapping)
   - Recommendation: Implement a `_parse_ai_response(text)` helper that strips code fences and retries extraction. Log raw response on parse failure for monitoring. LOW risk but worth a defensive parse.

2. **Priority override UX**
   - What we know: User wants manual override supported (P1->P3 etc.)
   - What's unclear: Whether to use a slash command or a select menu/button on the analysis embed
   - Recommendation: Use a Discord select menu (dropdown) added to the analysis embed message view, with P1-P4 options. This is more discoverable than a slash command and keeps the interaction in-context. Falls under Claude's Discretion.

3. **Thumbs-down reaction tracking implementation**
   - What we know: Team should be able to react with thumbs-down to flag bad analysis, bot logs it
   - What's unclear: Whether to use `on_raw_reaction_add` event listener or a dedicated button
   - Recommendation: Use `on_raw_reaction_add` event in the AI analysis cog, filtering for the analysis message ID and thumbs-down emoji. Log to console and optionally to a new `analysis_feedback` table. This is lightweight and non-intrusive.

## Sources

### Primary (HIGH confidence)
- Context7 `/anthropics/anthropic-sdk-python` -- AsyncAnthropic client, messages.create, error handling, retry config, token usage
- Context7 `/rapptz/discord.py` -- DynamicItem, interaction.response.defer, thread.send, message.edit, ephemeral messages
- Anthropic official pricing page (https://platform.claude.com/docs/en/about-claude/pricing) -- Model pricing, token costs
- Anthropic official models page (https://platform.claude.com/docs/en/docs/about-claude/models) -- Model IDs, context windows, max output

### Secondary (MEDIUM confidence)
- WebSearch verified model naming and SDK version (anthropic >=0.80.0 current as of Feb 2026)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Anthropic SDK is well-documented with Context7 snippets; discord.py already proven in Phase 1
- Architecture: HIGH -- Service layer pattern is standard; all Discord APIs verified in Phase 1 codebase
- Pitfalls: HIGH -- All pitfalls derived from verified API behavior (3-second interaction timeout, JSON parsing, error handling)
- Database schema: MEDIUM -- Column additions are straightforward but migration strategy for existing data needs validation during implementation

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (stable domain, 30-day validity)
