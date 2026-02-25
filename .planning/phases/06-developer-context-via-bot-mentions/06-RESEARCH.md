# Phase 6: Developer Context via @Bot Mentions - Research

**Researched:** 2026-02-25
**Domain:** Discord bot event handling, SQLite schema extension, AI prompt engineering
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Trigger:** Only messages that @mention the bot in a bug thread are treated as context
- **Bot confirmation:** Emoji reaction (pencil) AND short text reply ("Context saved (N notes for this bug)")
- **Empty mentions:** Bot shows a brief help message instead of saving
- **Timing:** Context accepted any time (Claude's discretion -- likely always accept)
- **Storage:** New SQLite table `developer_notes` with bug_id, author, content, timestamp (consistent with existing architecture)
- **No limit** on number of notes per bug
- **Editable and deletable:** If a Discord message is edited or deleted, the stored note is updated/removed accordingly
- **Attachments:** Claude's discretion (likely store attachment URLs alongside text)
- **Context flows into BOTH modes:** Anthropic (in the system prompt) and Copilot (in issue body + custom_instructions)
- **Developer context is presented as equal to AI analysis** (neither has priority -- the AI agent weighs both)
- **Prompt positioning:** Claude's discretion (likely a dedicated "Developer Notes" section)
- **Traceability:** PR body includes a "Developer Notes" section listing all context with author and timestamp
- **Draft Fix warning:** If no developer context exists when Draft Fix is clicked, show a confirmation hint ("No developer context provided. Continue anyway?")
- **Permissions:** Only users with the configured Developer role can add context
- **Overview:** Available via both a slash command AND a counter in the bug embed
- **Bug embed:** Shows a compact "pencil N Developer Notes" field (counter only, no preview)
- **Slash command:** Shows all collected notes for a bug with author and timestamp

### Claude's Discretion
- Exact prompt positioning of developer context relative to AI analysis
- Whether to store attachment URLs alongside text content
- Whether to accept context after Draft Fix has been triggered (recommended: always accept)
- Help message wording for empty mentions

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Summary

Phase 6 adds a human-in-the-loop context layer to the bug fix pipeline. Developers @mention the bot in a bug thread to add context notes (thoughts, theories, code pointers) that get stored in SQLite and included when Draft Fix generates code. This requires enabling the `message_content` privileged intent (currently disabled), adding a new `developer_notes` table, creating a new cog for mention handling, and injecting developer notes into both Anthropic and Copilot code fix prompts.

The implementation is straightforward because the existing codebase provides all the foundational patterns: role checking (used by `BugActionButton.interaction_check`), schema migration (used by Phases 2 and 3), SQLite CRUD (used by `BugRepository`), embed builders (used everywhere), and prompt construction (used by `CodeFixService._build_code_fix_prompt` and `CopilotFixService._build_custom_instructions`). The main new capability is the `on_message` event listener, which the bot has not used before.

**Primary recommendation:** Create a `DeveloperNotesCog` with `on_message` / `on_raw_message_edit` / `on_raw_message_delete` listeners, a `DeveloperNotesRepository` for CRUD, and modify both fix services' prompt builders to include developer notes when present.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.x (already installed) | on_message events, Thread detection, mention checking, emoji reactions | Already used throughout project |
| aiosqlite | (already installed) | developer_notes table CRUD | Already used for all DB operations |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| discord.app_commands | (bundled with discord.py) | /view-notes slash command | For the slash command to view all notes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New SQLite table | JSON field on bugs table | Separate table is cleaner for N notes per bug, supports edit/delete tracking by Discord message_id |
| on_message event | Slash command for adding notes | User decision locks mention-based trigger; slash command is for viewing only |

**Installation:** No new dependencies needed -- all libraries are already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/
  cogs/
    developer_notes.py     # New cog: on_message listener + /view-notes command
  models/
    developer_notes.py     # New repository: DeveloperNotesRepository CRUD
    database.py            # Modified: add developer_notes schema + migration
  services/
    code_fix_service.py    # Modified: inject developer notes into prompt
    copilot_fix_service.py # Modified: inject developer notes into issue body + instructions
  utils/
    embeds.py              # Modified: add developer notes counter to summary embed
    github_templates.py    # Modified: add developer notes section to PR body
  views/
    bug_buttons.py         # Modified: Draft Fix handler fetches notes + shows warning
  bot.py                   # Modified: enable message_content intent
```

### Pattern 1: Enabling message_content Intent
**What:** The bot currently uses `discord.Intents.default()` which does NOT include `message_content`. Phase 6 needs to read @mention message text, which requires this privileged intent.
**When to use:** When you need to read the content of messages (not just reactions/interactions).
**Example:**
```python
# Source: discord.py official docs + Context7 /rapptz/discord.py
# In bot.py __init__:
intents = discord.Intents.default()
intents.message_content = True  # Phase 6: read @mention content
super().__init__(command_prefix="!", intents=intents)
```
**IMPORTANT:** This is a privileged intent. The Discord Developer Portal must also have "Message Content Intent" toggled ON for the bot application. For bots in fewer than 100 guilds, this is a simple toggle. For 100+ guilds, Discord requires verification with a valid use case.

### Pattern 2: @Mention Detection in Thread via on_message Cog Listener
**What:** Detect when the bot is @mentioned in a bug thread, extract the context text, and store it.
**When to use:** For the core mention-to-note pipeline.
**Example:**
```python
# Source: discord.py docs, verified via Context7
class DeveloperNotesCog(commands.Cog):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Skip bot's own messages
        if message.author.bot:
            return

        # Only process messages that @mention the bot
        if self.bot.user not in message.mentions:
            return

        # Only process messages in threads
        if not isinstance(message.channel, discord.Thread):
            return

        # Look up which bug this thread belongs to
        bug = await self.bot.bug_repo.get_bug_by_thread_id(message.channel.id)
        if bug is None:
            return  # Not a bug thread

        # Role check
        role_name = self.bot.config.DEVELOPER_ROLE_NAME
        required_role = discord.utils.get(message.guild.roles, name=role_name)
        if required_role is None or required_role not in message.author.roles:
            return  # Silently ignore non-developers

        # Extract content (strip the mention itself)
        content = message.content
        # Remove the bot mention pattern (<@BOT_ID> or <@!BOT_ID>)
        content = content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()

        if not content and not message.attachments:
            # Empty mention -- show help message
            await message.reply("Mention me with a message to add developer context for this bug. ...")
            return

        # Store note
        # ... (DeveloperNotesRepository.create_note)

        # React with pencil emoji + reply with count
        await message.add_reaction("\U0001f4dd")
        note_count = await self.notes_repo.count_notes(bug["id"])
        await message.reply(f"\U0001f4dd Context saved ({note_count} notes for this bug)")
```

### Pattern 3: Edit/Delete Tracking via Raw Events
**What:** Use `on_raw_message_edit` and `on_raw_message_delete` to sync note changes when Discord messages are edited or deleted.
**When to use:** For maintaining consistency between Discord messages and stored notes.
**Example:**
```python
# Source: discord.py docs -- raw events work even if message is not in cache
@commands.Cog.listener()
async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
    # Try to delete the note by Discord message_id
    deleted = await self.notes_repo.delete_note_by_message_id(payload.message_id)
    if deleted:
        logger.info("Developer note deleted (Discord msg %d)", payload.message_id)

@commands.Cog.listener()
async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
    # 'content' key may be absent for embed-only edits
    data = payload.data
    if "content" not in data:
        return  # Embed-only edit, ignore

    new_content = data["content"]
    # Strip mention from new content
    # ... same stripping logic
    updated = await self.notes_repo.update_note_by_message_id(
        payload.message_id, new_content
    )
    if updated:
        logger.info("Developer note updated (Discord msg %d)", payload.message_id)
```
**Key insight:** We use `on_raw_message_edit` / `on_raw_message_delete` (not `on_message_edit` / `on_message_delete`) because the raw variants fire regardless of whether the message is in the internal cache. Since bug threads may be old and messages may not be cached, raw events are essential for reliability.

### Pattern 4: SQLite Schema and Migration
**What:** Add `developer_notes` table and migration function following the existing pattern.
**When to use:** For the new table.
**Example:**
```python
# Source: Existing database.py pattern (migrate_add_analysis_columns, migrate_add_github_columns)
DEVELOPER_NOTES_SCHEMA = """
CREATE TABLE IF NOT EXISTS developer_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bug_id INTEGER NOT NULL REFERENCES bugs(id),
    discord_message_id INTEGER UNIQUE NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    attachment_urls TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_developer_notes_bug_id ON developer_notes(bug_id);
CREATE INDEX IF NOT EXISTS idx_developer_notes_message_id ON developer_notes(discord_message_id);
"""

async def migrate_add_developer_notes(db: aiosqlite.Connection) -> None:
    """Add Phase 6 developer_notes table if missing. Idempotent."""
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='developer_notes'"
    ) as cursor:
        if await cursor.fetchone() is not None:
            return  # Table already exists
    await db.executescript(DEVELOPER_NOTES_SCHEMA)
    await db.commit()
```
Also need an index on bugs.thread_id (missing today):
```python
# Add to migration:
CREATE INDEX IF NOT EXISTS idx_bugs_thread_id ON bugs(thread_id);
```

### Pattern 5: Injecting Developer Notes into Code Fix Prompt
**What:** Add a "Developer Notes" section to the Anthropic system prompt and Copilot issue body/instructions.
**When to use:** During Draft Fix generation.
**Example for Anthropic mode:**
```python
# In CodeFixService._build_code_fix_prompt, after the AI Analysis section:
def _build_developer_notes_section(self, notes: list[dict]) -> str:
    if not notes:
        return ""
    lines = ["\nDeveloper Notes:"]
    for note in notes:
        author = note.get("author_name", "Unknown")
        content = note.get("content", "")
        timestamp = note.get("created_at", "")
        lines.append(f"  [{author} at {timestamp}]: {content}")
    return "\n".join(lines)
```
**Example for Copilot mode:**
```python
# In CopilotFixService._build_issue_body, add a section:
# In CopilotFixService._build_custom_instructions, append notes summary
```

### Pattern 6: Bug Embed Notes Counter
**What:** Add a "Developer Notes" field to the summary embed showing the count.
**When to use:** Every time the summary embed is built/rebuilt.
**Example:**
```python
# In build_summary_embed, after the GitHub PR field:
# note_count is passed as a parameter or fetched
if note_count and note_count > 0:
    embed.add_field(
        name="Developer Notes",
        value=f"\U0001f4dd {note_count}",
        inline=True,
    )
```

### Anti-Patterns to Avoid
- **Storing full message content including mention markup:** Strip the `<@BOT_ID>` mention before storing. Users don't want to see raw mention syntax in PR bodies.
- **Using on_message_edit instead of on_raw_message_edit:** The non-raw variant only fires if the message is in cache. Bug thread messages are often not cached.
- **Adding notes to the bugs table directly:** A separate table is correct for N notes per bug with independent CRUD.
- **Blocking on_message with slow DB queries:** All DB operations are async via aiosqlite, so this is already handled by the existing architecture.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mention text extraction | Custom regex parser | String.replace with `<@BOT_ID>` and `<@!BOT_ID>` | Discord mentions have only two formats; regex is overkill |
| Message edit/delete tracking | Custom polling | `on_raw_message_edit` / `on_raw_message_delete` events | Discord gateway pushes these events automatically |
| Thread-to-bug mapping | Thread name parsing | `bugs.thread_id` column lookup | Already stored in DB since Phase 1 |
| Role checking | Custom permission system | `discord.utils.get(guild.roles, name=...)` pattern | Already used by `BugActionButton.interaction_check` |

**Key insight:** The existing codebase already has all foundational patterns. Phase 6 is primarily wiring them together with a new event type (on_message) and a new table.

## Common Pitfalls

### Pitfall 1: Forgetting to Enable message_content in Discord Developer Portal
**What goes wrong:** Bot receives on_message events but `message.content` is empty string.
**Why it happens:** Even if code sets `intents.message_content = True`, the Discord Developer Portal must also have the "Message Content Intent" toggle enabled for the bot application.
**How to avoid:** Document the portal toggle requirement. Test with an actual @mention before marking Phase 6 complete.
**Warning signs:** `message.content` is always `""` even when messages have text.

### Pitfall 2: on_message Blocking process_commands
**What goes wrong:** If using `commands.Bot` and overriding `on_message`, prefix commands stop working.
**Why it happens:** `commands.Bot` requires `await self.bot.process_commands(message)` at the end of on_message.
**How to avoid:** Since we're using a **Cog listener** (`@commands.Cog.listener()`), this is NOT a problem -- cog listeners don't override the bot's on_message, they add to it. The bot doesn't use prefix commands anyway.
**Warning signs:** Other message-based features stop working (not applicable here since no prefix commands exist).

### Pitfall 3: Race Condition Between Note Save and Draft Fix Trigger
**What goes wrong:** Developer adds context and immediately clicks Draft Fix. Note may not be committed to DB yet when fix service reads notes.
**Why it happens:** Discord event processing is async; button clicks and messages are independent events.
**How to avoid:** The `on_message` handler uses `await db.commit()` synchronously before replying. By the time the user sees the confirmation, the note is committed. The Draft Fix button handler then reads notes after its own defer, which happens later.
**Warning signs:** Notes missing from PR body despite confirmation message.

### Pitfall 4: Embed-Only Edits Triggering Note Updates
**What goes wrong:** Discord fires `on_raw_message_edit` when embeds are added/updated (e.g., link preview). If not filtered, this overwrites the note with empty content.
**Why it happens:** `on_raw_message_edit` fires for ANY message update, including embed-only updates where `data['content']` may be absent.
**How to avoid:** Check `if 'content' not in payload.data: return` before processing edits.
**Warning signs:** Developer notes losing their content randomly.

### Pitfall 5: Draft Fix Confirmation Dialog Blocking UX
**What goes wrong:** The "No developer context provided. Continue anyway?" confirmation adds friction when context is intentionally not needed (e.g., clear bugs).
**Why it happens:** User decision requires the warning.
**How to avoid:** Make it a simple ephemeral followup with a "Continue" button, not a blocking modal. User can click the original Draft Fix button again to proceed.
**Warning signs:** Users complaining about extra clicks.

### Pitfall 6: Missing bug lookup by thread_id
**What goes wrong:** Cannot map a thread to its bug when processing @mentions.
**Why it happens:** `BugRepository` has no `get_bug_by_thread_id` method, and there's no index on `bugs.thread_id`.
**How to avoid:** Add both the method and the index in the database migration for Phase 6.
**Warning signs:** All @mentions in bug threads are silently ignored.

## Code Examples

Verified patterns from the existing codebase:

### DeveloperNotesRepository (New)
```python
# Following existing BugRepository pattern in src/models/bug.py
class DeveloperNotesRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        self.db.row_factory = aiosqlite.Row

    async def create_note(
        self, bug_id: int, discord_message_id: int,
        author_id: int, author_name: str, content: str,
        attachment_urls: str | None = None,
    ) -> dict:
        now = _utcnow_iso()
        await self.db.execute(
            """INSERT INTO developer_notes
               (bug_id, discord_message_id, author_id, author_name,
                content, attachment_urls, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (bug_id, discord_message_id, author_id, author_name,
             content, attachment_urls, now, now),
        )
        await self.db.commit()
        return await self.get_note_by_message_id(discord_message_id)

    async def get_notes_for_bug(self, bug_id: int) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM developer_notes WHERE bug_id = ? ORDER BY created_at ASC",
            (bug_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

    async def count_notes(self, bug_id: int) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM developer_notes WHERE bug_id = ?",
            (bug_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def get_note_by_message_id(self, message_id: int) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM developer_notes WHERE discord_message_id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_note_by_message_id(
        self, message_id: int, new_content: str
    ) -> bool:
        now = _utcnow_iso()
        cursor = await self.db.execute(
            "UPDATE developer_notes SET content = ?, updated_at = ? WHERE discord_message_id = ?",
            (new_content, now, message_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def delete_note_by_message_id(self, message_id: int) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM developer_notes WHERE discord_message_id = ?",
            (message_id,),
        )
        await self.db.commit()
        return cursor.rowcount > 0
```

### BugRepository.get_bug_by_thread_id (New method)
```python
# Add to src/models/bug.py
async def get_bug_by_thread_id(self, thread_id: int) -> dict | None:
    """Return a bug by its Discord thread_id, or None."""
    async with self.db.execute(
        "SELECT * FROM bugs WHERE thread_id = ?", (thread_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None
```

### Developer Notes in Anthropic Prompt
```python
# In CodeFixService._build_code_fix_prompt, insert after AI Analysis section:
# developer_notes parameter is a list[dict] passed from the Draft Fix handler
if developer_notes:
    notes_lines = []
    for note in developer_notes:
        author = note.get("author_name", "Unknown")
        content = note.get("content", "")
        timestamp = note.get("created_at", "")
        notes_lines.append(f"  [{author} at {timestamp}]: {content}")
    notes_section = "\n".join(notes_lines)
    prompt += (
        f"\n"
        f"Developer Notes (from team members):\n"
        f"{notes_section}\n"
    )
```

### Developer Notes in Copilot Issue Body and Instructions
```python
# In CopilotFixService._build_issue_body, add before the footer:
if developer_notes:
    body += "\n### Developer Notes\n"
    for note in developer_notes:
        body += f"- **{note['author_name']}:** {note['content']}\n"

# In CopilotFixService._build_custom_instructions, append:
if developer_notes:
    notes_summary = "; ".join(
        f"{n['author_name']}: {n['content']}" for n in developer_notes
    )
    parts.append(f"Developer notes: {notes_summary}")
```

### Developer Notes in PR Body
```python
# In github_templates.py build_code_fix_pr_body, add a new section:
if developer_notes:
    sections.extend(["", "### Developer Notes"])
    for note in developer_notes:
        author = note.get("author_name", "Unknown")
        content = note.get("content", "")
        timestamp = note.get("created_at", "")
        sections.append(f"- **{author}** ({timestamp}): {content}")
```

### Summary Embed Notes Counter
```python
# In embeds.py build_summary_embed, add after PR field:
# note_count passed as keyword argument or fetched from context
if note_count is not None and note_count > 0:
    embed.add_field(
        name="Developer Notes",
        value=f"\U0001f4dd {note_count}",
        inline=True,
    )
```

### /view-notes Slash Command
```python
# Following existing /set-priority pattern in ai_analysis.py
@app_commands.command(
    name="view-notes",
    description="View developer context notes for a bug",
)
@app_commands.describe(bug_id="The bug hash ID (e.g., a3f2b1c0)")
async def view_notes(
    self, interaction: discord.Interaction, bug_id: str
) -> None:
    await interaction.response.defer(ephemeral=True)
    # Role check (same pattern as set-priority)
    # Fetch bug -> fetch notes -> format as embed or message
    # Handle no notes case
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bot only uses interactions (buttons/slash) | Adding on_message event listening | Phase 6 | Requires message_content privileged intent |
| Notes stored in thread messages only | Notes stored in SQLite + synced | Phase 6 | Enables structured querying and prompt injection |
| Draft Fix uses only AI analysis context | Draft Fix uses AI analysis + developer notes | Phase 6 | Richer context for code generation |

**Deprecated/outdated:**
- `on_message_edit` / `on_message_delete` (non-raw): Unreliable for messages not in cache. Use raw variants instead.
- `message.clean_content` for mention stripping: Strips ALL mentions, not just the bot's. Use targeted string replacement instead.

## Open Questions

1. **Summary embed rebuild after note addition**
   - What we know: The summary embed should show a note counter. When a note is added, the embed needs updating.
   - What's unclear: How to efficiently get the bug's channel message to edit the embed. The bug record stores `message_id` and `channel_id`, so it's possible but adds a Discord API call per note.
   - Recommendation: Update the embed on note creation. The existing codebase does this pattern for analyze/create_issue/draft_fix handlers. The channel_id + message_id lookup is proven.

2. **Attachment URL storage format**
   - What we know: Discord attachments have URLs. Decision says "Claude's discretion."
   - What's unclear: Whether to store as JSON array or newline-separated string.
   - Recommendation: Store as JSON array string (consistent with console_logs pattern in the existing schema). Parse with `_parse_json_field` from embeds.py.

3. **Draft Fix "no context" warning UX**
   - What we know: User decision requires a confirmation hint when no developer context exists.
   - What's unclear: Whether to use a modal, an ephemeral message with a button, or just an ephemeral warning.
   - Recommendation: Use an ephemeral followup message with text like "No developer context provided. Click Draft Fix again to proceed." This avoids complex modal/button state and follows the existing pattern of ephemeral confirmations.

## Sources

### Primary (HIGH confidence)
- Context7 `/rapptz/discord.py` -- on_message event handling, message.mentions property, intents configuration, Thread detection, raw message events
- Existing codebase analysis:
  - `src/bot.py` -- current intent configuration (no message_content)
  - `src/models/database.py` -- schema migration pattern
  - `src/models/bug.py` -- BugRepository CRUD pattern, missing get_bug_by_thread_id
  - `src/services/code_fix_service.py` -- `_build_code_fix_prompt` injection point (line 315-381)
  - `src/services/copilot_fix_service.py` -- `_build_issue_body` (line 247-262) and `_build_custom_instructions` (line 264-277) injection points
  - `src/utils/github_templates.py` -- `build_code_fix_pr_body` (line 380-478) injection point
  - `src/utils/embeds.py` -- `build_summary_embed` (line 153-247) for notes counter
  - `src/views/bug_buttons.py` -- `_handle_draft_fix` (line 445-806) for warning injection
  - `src/cogs/ai_analysis.py` -- `/set-priority` pattern for slash command reference

### Secondary (MEDIUM confidence)
- discord.py official documentation (discordpy.readthedocs.io) -- message_content intent requirements, raw event payloads
- Discord Developer Portal documentation -- privileged intent toggle requirement

### Tertiary (LOW confidence)
- None -- all findings verified against primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used in the project
- Architecture: HIGH -- all patterns derived from existing codebase, verified against discord.py docs
- Pitfalls: HIGH -- pitfalls 1-4 verified against discord.py docs; pitfall 5-6 derived from codebase analysis

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable -- discord.py 2.x is mature, no breaking changes expected)
