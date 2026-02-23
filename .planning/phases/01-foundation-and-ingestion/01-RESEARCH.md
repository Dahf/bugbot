# Phase 1: Foundation and Ingestion - Research

**Researched:** 2026-02-23
**Domain:** Discord bot foundation (discord.py), webhook ingestion (aiohttp), state persistence (SQLite/aiosqlite)
**Confidence:** HIGH

## Summary

Phase 1 builds the foundational Discord bot that receives bug reports from a Supabase edge function webhook, displays them as rich embeds with action buttons, creates per-bug discussion threads, and persists all state in SQLite. The primary technical challenges are: (1) running an aiohttp webhook server alongside the discord.py event loop, (2) implementing persistent/dynamic button views that survive bot restarts, and (3) designing a SQLite schema that supports the full bug lifecycle.

The discord.py ecosystem (v2.6.4) provides first-class support for all needed features: `DynamicItem` (v2.4+) for persistent buttons with encoded bug IDs, `discord.Embed` for rich formatting with color-coded statuses, and `Message.create_thread()` for per-bug threads. The aiohttp web server can run alongside discord.py using `AppRunner`/`TCPSite` (non-blocking), and aiosqlite provides async SQLite access that won't block the event loop.

The webhook payload will come from a Supabase edge function (TypeScript/Deno) that makes an HTTP POST to our bot's endpoint. Since this is a custom edge function (not a raw Supabase database webhook), the exact payload schema will be defined by the user's existing code. The bot should validate requests using HMAC-SHA256 with a shared secret, store the raw payload immediately ("store-then-process"), and then process it asynchronously.

**Primary recommendation:** Use discord.py 2.6.4 with DynamicItem for persistent buttons, aiohttp AppRunner for the webhook server, and aiosqlite with WAL mode for state persistence. Structure the bot with Cogs for clean separation of concerns.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Embed presentation:**
- Color coding by status: color changes as bug progresses through workflow (e.g., red=new, blue=analyzing, green=resolved)
- Summary embed in main channel: show title, user, status, and severity only. Full details (console logs, device info, steps to reproduce) go in the thread
- Short hash IDs for bug identification (e.g., `#a3f2`) -- not sequential
- Embed title format includes the hash ID prominently

**Webhook payload:**
- Existing Supabase webhook -- payload structure to be provided before planning
- Single Supabase project: one webhook secret, one Discord channel
- Accept and fill gaps: store whatever fields are available, show "N/A" or "Unknown" for missing fields -- never reject a bug report

**Thread behavior:**
- Thread per bug (not a text channel)
- Thread naming: hash + title (e.g., "#a3f2 -- App crashes on login")
- First thread message: full bug details followed by a template-based summary (structured from available fields). AI summary comes in Phase 2
- Auto-archive after 30 days of inactivity (use longest Discord auto-archive option available; researcher to verify Discord API limits for the server's boost level)

**Button interactions:**
- Dismiss: marks as dismissed with greyed/strikethrough styling -- embed stays visible in channel, data preserved in DB
- Buttons stay active after use -- users can re-trigger actions if needed
- Analyze, Create Issue, and Draft Fix buttons: shown but disabled/greyed out in Phase 1 (functionality comes in Phases 2-3)
- Button clicks are role-gated: only users with a specific Discord role (e.g., "Developer") can interact with bug report buttons

### Claude's Discretion

- Emoji/icon usage in embed fields for visual distinction
- Exact embed field ordering and formatting
- Specific colors for each status state
- Template summary format in thread first message

### Deferred Ideas (OUT OF SCOPE)

- AI-generated summary in bug threads -- Phase 2 (AI Analysis)
- Multi-project webhook support -- potential future enhancement

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FOUND-01 | Bot receives bug reports from Supabase webhook with secret validation | aiohttp AppRunner/TCPSite for webhook server; HMAC-SHA256 validation pattern; store-then-process reliability |
| FOUND-02 | Bot displays bug reports as rich Discord embeds (description, user, device, time, console logs) | discord.Embed with color-coded status, up to 25 fields, 6000 char total limit; summary in channel, details in thread |
| FOUND-03 | Bot auto-creates a Discord thread for each bug report for dev discussion | Message.create_thread() with auto_archive_duration; max 7 days (10080 min) requires Level 2 boost |
| FOUND-04 | Bot presents action buttons on each report (Analyze, Create Issue, Draft Fix, Dismiss) | DynamicItem with template regex for persistent buttons; disabled=True for Phase 2-3 buttons; interaction_check for role gating |
| FOUND-05 | Bot persists all bug data and state in SQLite (survives restarts) | aiosqlite with WAL mode; schema for bugs, status history, message/thread references |
| FOUND-06 | Button interactions remain functional after bot restarts (persistent views) | DynamicItem registered via add_dynamic_items in setup_hook; custom_id encodes bug hash + action |
| FOUND-07 | Each bug has a tracked status (received, analyzing, triaged, issue_created, fix_drafted, resolved) | SQLite status column with enum-like values; status history table for audit trail; embed color updates on status change |
| FOUND-08 | Bot handles webhook delivery failures gracefully (store-then-process pattern) | Immediate 200 response + async processing; asyncio.Queue for internal processing; error logging and retry |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.6.4 | Discord API wrapper | Official, actively maintained, first-class support for Views, DynamicItem, Embeds, Threads |
| aiohttp | 3.13.3 | HTTP server for webhook endpoint | Ships with discord.py as dependency; AppRunner enables non-blocking server alongside bot |
| aiosqlite | 0.22.1 | Async SQLite access | Non-blocking DB access for asyncio bots; mirrors stdlib sqlite3 API; released Dec 2025 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | latest | Load .env files for config | Store Discord token, webhook secret, channel IDs securely |

### Not Needed (Covered by stdlib)
| Capability | stdlib Module | Notes |
|------------|---------------|-------|
| HMAC validation | `hmac`, `hashlib` | HMAC-SHA256 for webhook secret verification |
| Short hash IDs | `uuid` or `secrets` | `uuid.uuid4().hex[:8]` or `secrets.token_hex(4)` for 8-char hex IDs |
| JSON handling | `json` | Webhook payload parsing |
| Logging | `logging` | Structured logging throughout |
| Async queue | `asyncio.Queue` | Store-then-process webhook pattern |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| aiosqlite | SQLAlchemy async | Overkill for single-table SQLite; adds complexity without benefit at this scale |
| aiohttp server | FastAPI/Quart | Extra dependency; aiohttp already ships with discord.py and integrates naturally |
| DynamicItem | Persistent Views + DB lookup | DynamicItem is simpler -- encodes state in custom_id, no DB round-trip per button click |

**Installation:**
```bash
pip install discord.py aiosqlite python-dotenv
```

Note: `aiohttp` is already a dependency of `discord.py` and does not need separate installation.

## Architecture Patterns

### Recommended Project Structure
```
src/
    bot.py               # Bot class, setup_hook, main entry point
    config.py            # Configuration from env vars
    cogs/
        webhook.py       # aiohttp webhook server cog
        bug_reports.py   # Bug report embed/thread/button handling
    models/
        database.py      # Database connection, schema, migrations
        bug.py           # Bug data model and queries
    views/
        bug_buttons.py   # DynamicItem button definitions
    utils/
        embeds.py        # Embed builder helpers
        hashing.py       # Short hash ID generation
        webhook_auth.py  # HMAC validation
```

### Pattern 1: Bot Class with setup_hook
**What:** Subclass `commands.Bot` with async `setup_hook` for initialization
**When to use:** Always -- this is the modern discord.py pattern
**Example:**
```python
# Source: discord.py official examples + docs
import discord
from discord.ext import commands

class BugBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # message_content NOT needed -- we use buttons/interactions, not prefix commands
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load cogs
        await self.load_extension("cogs.webhook")
        await self.load_extension("cogs.bug_reports")

        # Register dynamic items for persistent buttons
        self.add_dynamic_items(BugActionButton)

        # Initialize database
        self.db = await setup_database()
```

### Pattern 2: DynamicItem for Persistent Buttons
**What:** Encode bug ID and action type in button custom_id using regex pattern matching
**When to use:** For all bug report action buttons -- survives restarts without DB lookup
**Example:**
```python
# Source: discord.py examples/views/persistent.py
import re
import discord

class BugActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"bug:(?P<action>\w+):(?P<bug_id>[a-f0-9]+)"
):
    def __init__(self, action: str, bug_id: str, *, disabled: bool = False):
        label_map = {
            "analyze": "Analyze",
            "create_issue": "Create Issue",
            "draft_fix": "Draft Fix",
            "dismiss": "Dismiss",
        }
        style_map = {
            "analyze": discord.ButtonStyle.primary,
            "create_issue": discord.ButtonStyle.primary,
            "draft_fix": discord.ButtonStyle.primary,
            "dismiss": discord.ButtonStyle.danger,
        }
        super().__init__(
            discord.ui.Button(
                label=label_map[action],
                style=style_map[action],
                custom_id=f"bug:{action}:{bug_id}",
                disabled=disabled,
            )
        )
        self.action = action
        self.bug_id = bug_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        action = match["action"]
        bug_id = match["bug_id"]
        return cls(action, bug_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Role gating: check if user has the required role
        required_role = discord.utils.get(interaction.guild.roles, name="Developer")
        if required_role is None or required_role not in interaction.user.roles:
            await interaction.response.send_message(
                "You need the Developer role to interact with bug reports.",
                ephemeral=True,
            )
            return False
        return True

    async def callback(self, interaction: discord.Interaction):
        if self.action == "dismiss":
            # Handle dismiss -- update DB, update embed
            await self.handle_dismiss(interaction)
        else:
            # Phase 2-3 actions -- should be disabled, but handle gracefully
            await interaction.response.send_message(
                f"The {self.action} feature is coming in a future update.",
                ephemeral=True,
            )
```

### Pattern 3: aiohttp Webhook Server as Cog
**What:** Run aiohttp web server alongside discord.py using AppRunner/TCPSite
**When to use:** For receiving Supabase webhook POSTs
**Example:**
```python
# Source: community pattern verified across multiple sources
from aiohttp import web
from discord.ext import commands
import asyncio

class WebhookServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.site = None

    async def cog_load(self):
        app = web.Application()
        app.router.add_post("/webhook/bug-report", self.handle_webhook)
        app.router.add_get("/health", self.health_check)

        runner = web.AppRunner(app)
        await runner.setup()
        self.site = web.TCPSite(runner, "0.0.0.0", 8080)
        await self.site.start()

    async def cog_unload(self):
        if self.site:
            await self.site.stop()

    async def handle_webhook(self, request: web.Request) -> web.Response:
        # 1. Validate HMAC signature
        # 2. Read and parse JSON body
        # 3. Store raw payload in DB immediately (store-then-process)
        # 4. Queue for async processing
        # 5. Return 200 immediately
        raw_body = await request.read()

        if not self.validate_signature(request, raw_body):
            return web.Response(status=401, text="Invalid signature")

        payload = json.loads(raw_body)

        # Store raw, then queue for processing
        bug_id = await self.bot.db.store_raw_report(payload)
        await self.bot.processing_queue.put(bug_id)

        return web.json_response({"status": "received", "bug_id": bug_id})

    def validate_signature(self, request, body: bytes) -> bool:
        signature = request.headers.get("X-Webhook-Signature", "")
        expected = hmac.new(
            self.bot.config.webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
```

### Pattern 4: Store-Then-Process for Webhook Reliability
**What:** Immediately store raw webhook data, return 200, process asynchronously
**When to use:** Always for webhook handling -- prevents data loss on processing errors
**Example:**
```python
# Source: webhook best practices (hookdeck.com, oneuptime.com)
class BugProcessor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.processing_queue = asyncio.Queue()

    async def cog_load(self):
        self.process_task = self.bot.loop.create_task(self.process_loop())

    async def cog_unload(self):
        self.process_task.cancel()

    async def process_loop(self):
        await self.bot.wait_until_ready()
        while True:
            bug_id = await self.bot.processing_queue.get()
            try:
                await self.process_bug_report(bug_id)
            except Exception as e:
                logging.error(f"Failed to process bug {bug_id}: {e}")
                # Mark as failed in DB for retry
                await self.bot.db.mark_processing_failed(bug_id, str(e))
            finally:
                self.bot.processing_queue.task_done()
```

### Anti-Patterns to Avoid
- **Blocking the event loop with sqlite3:** Always use aiosqlite, never stdlib sqlite3 directly in async code
- **Processing webhooks synchronously:** Never do heavy processing before returning HTTP 200 -- store first, process later
- **Hardcoding custom_ids:** Use DynamicItem with regex patterns, not individual persistent views per bug
- **Using prefix commands:** This bot uses buttons/interactions; do NOT enable message_content intent (not needed, and Discord may reject the application)
- **Global state in module scope:** Store state on the bot instance or in the database, not in module-level variables

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Persistent buttons | Manual custom_id registry + DB lookup per click | `discord.ui.DynamicItem` | Built-in regex matching, automatic dispatch, no DB round-trip |
| Webhook signature validation | Custom crypto implementation | `hmac.compare_digest()` with `hmac.new()` | Timing-safe comparison prevents timing attacks |
| Async SQLite | Thread pool wrapper around sqlite3 | `aiosqlite` | Battle-tested asyncio bridge, handles thread management |
| HTTP server alongside bot | Manual asyncio.create_task with raw sockets | `aiohttp.web.AppRunner` + `TCPSite` | Proper lifecycle management, graceful shutdown |
| Embed builder | Raw dict construction for Discord API | `discord.Embed` class methods | Type-safe, handles limits, proper serialization |

**Key insight:** discord.py 2.4+ DynamicItem eliminates the most complex aspect of persistent button bots. Without it, you'd need a database lookup for every button click to reconstruct state. With it, the bug ID is encoded directly in the custom_id and parsed via regex.

## Common Pitfalls

### Pitfall 1: Thread Auto-Archive Duration Depends on Boost Level
**What goes wrong:** Bot tries to set `auto_archive_duration=10080` (7 days) but the server doesn't have Level 2 boost, causing an API error.
**Why it happens:** Discord gates thread archive durations by server boost level:
- Free servers: max 1440 minutes (1 day)
- Level 1 boost: max 4320 minutes (3 days)
- Level 2 boost: max 10080 minutes (7 days)
**How to avoid:** The user requested "longest available." Use a fallback strategy: try 10080, catch the error, fall back to 4320, then 1440. Or check the guild's premium tier first via `guild.premium_tier`.
**Warning signs:** `HTTPException` with status 400 when creating threads.

### Pitfall 2: Forgetting to Register DynamicItems in setup_hook
**What goes wrong:** Buttons work when first sent but stop working after bot restart.
**Why it happens:** DynamicItem classes must be registered with `bot.add_dynamic_items(BugActionButton)` in `setup_hook()` before the bot connects. If not registered, discord.py doesn't know how to dispatch interactions to the correct handler.
**How to avoid:** Always register in `setup_hook()`, never conditionally.
**Warning signs:** "This interaction failed" error in Discord after bot restart.

### Pitfall 3: Custom ID Length Limit (100 characters)
**What goes wrong:** If bug IDs or action names are too long, the custom_id exceeds 100 characters and Discord rejects the component.
**Why it happens:** Discord enforces a hard 100-character limit on custom_id fields.
**How to avoid:** Use short hash IDs (4-8 hex chars) and short action names. Example: `bug:dismiss:a3f2b1c0` = 22 characters, well within limits.
**Warning signs:** API error on message send with components.

### Pitfall 4: Blocking the Event Loop with Synchronous SQLite
**What goes wrong:** Bot becomes unresponsive during database operations.
**Why it happens:** stdlib `sqlite3` blocks the thread. In an asyncio application, this freezes the entire event loop.
**How to avoid:** Use `aiosqlite` exclusively. Enable WAL mode for better concurrent read/write: `await db.execute("PRAGMA journal_mode=WAL")`.
**Warning signs:** Bot doesn't respond to interactions during DB-heavy operations; "This interaction failed" timeouts.

### Pitfall 5: Not Returning 200 Fast Enough from Webhook Endpoint
**What goes wrong:** Supabase edge function times out waiting for response, may retry and create duplicate bug reports.
**Why it happens:** Processing the bug report (creating embeds, threads, etc.) takes time. If you do it before responding, the webhook sender may time out.
**How to avoid:** Store-then-process pattern. Return 200 within milliseconds, process asynchronously via queue.
**Warning signs:** Duplicate bug reports, webhook delivery marked as failed on Supabase side.

### Pitfall 6: Embed Field/Character Limits
**What goes wrong:** Bot crashes or Discord rejects the message when console logs or descriptions are too long.
**Why it happens:** Discord embed limits: title 256 chars, description 4096 chars, field name 256 chars, field value 1024 chars, total across all fields 6000 chars, max 25 fields.
**How to avoid:** Truncate all fields before building the embed. Add "..." suffix for truncated content. Put full details in the thread message (which has the standard 2000-char message limit, or use multiple messages).
**Warning signs:** HTTPException 400 on message send.

### Pitfall 7: Race Condition on Bug Hash Collision
**What goes wrong:** Two bug reports get the same short hash ID.
**Why it happens:** 4-character hex IDs only have 65,536 possible values. With even modest volume, collisions happen (birthday problem).
**How to avoid:** Use 8-character hex IDs (4 bytes = ~4 billion combinations). Check for collisions in the database before assigning. Regenerate if collision detected.
**Warning signs:** Database unique constraint violation on insert.

## Code Examples

### Creating a Status-Colored Bug Report Embed
```python
# Source: discord.py docs + project CONTEXT.md decisions
import discord
from datetime import datetime

STATUS_COLORS = {
    "received":      discord.Colour(0xED4245),   # Red -- new/unprocessed
    "analyzing":     discord.Colour(0x3498DB),   # Blue -- being analyzed
    "triaged":       discord.Colour(0xE67E22),   # Orange -- triaged/prioritized
    "issue_created": discord.Colour(0x9B59B6),   # Purple -- GitHub issue exists
    "fix_drafted":   discord.Colour(0xF1C40F),   # Gold -- fix PR created
    "resolved":      discord.Colour(0x2ECC71),   # Green -- resolved
    "dismissed":     discord.Colour(0x95A5A6),   # Grey -- dismissed
}

STATUS_EMOJI = {
    "received":      "\U0001f534",  # Red circle
    "analyzing":     "\U0001f535",  # Blue circle
    "triaged":       "\U0001f7e0",  # Orange circle
    "issue_created": "\U0001f7e3",  # Purple circle
    "fix_drafted":   "\U0001f7e1",  # Yellow circle
    "resolved":      "\U0001f7e2",  # Green circle
    "dismissed":     "\u26aa",      # White circle
}

def build_summary_embed(bug: dict) -> discord.Embed:
    """Build the summary embed for the main channel.
    Shows: hash ID, title, user, status, severity only.
    """
    status = bug.get("status", "received")
    hash_id = bug["hash_id"]

    embed = discord.Embed(
        title=f"#{hash_id} -- {bug.get('title', 'Untitled Bug Report')}",
        color=STATUS_COLORS.get(status, discord.Colour.default()),
        timestamp=datetime.fromisoformat(bug.get("created_at", datetime.utcnow().isoformat())),
    )
    embed.add_field(
        name="Status",
        value=f"{STATUS_EMOJI.get(status, '')} {status.replace('_', ' ').title()}",
        inline=True,
    )
    embed.add_field(
        name="Severity",
        value=bug.get("severity", "Unknown"),
        inline=True,
    )
    embed.add_field(
        name="Reporter",
        value=bug.get("user_id", "Unknown"),
        inline=True,
    )
    embed.set_footer(text=f"Bug #{hash_id}")
    return embed
```

### Creating a Thread with Full Bug Details
```python
# Source: discord.py docs (Message.create_thread)
async def create_bug_thread(message: discord.Message, bug: dict, guild: discord.Guild):
    """Create a thread from the bug report message with full details."""
    hash_id = bug["hash_id"]
    title = bug.get("title", "Untitled Bug Report")
    thread_name = f"#{hash_id} -- {title}"[:100]  # Thread names max 100 chars

    # Determine best auto_archive_duration based on server boost level
    if guild.premium_tier >= 2:
        archive_duration = 10080  # 7 days
    elif guild.premium_tier >= 1:
        archive_duration = 4320   # 3 days
    else:
        archive_duration = 1440   # 1 day

    thread = await message.create_thread(
        name=thread_name,
        auto_archive_duration=archive_duration,
    )

    # Post full details as first thread message
    details = build_thread_details(bug)
    await thread.send(details)

    return thread

def build_thread_details(bug: dict) -> str:
    """Build the full details message for the thread."""
    sections = []
    sections.append(f"## Bug Report #{bug['hash_id']}")
    sections.append(f"**Title:** {bug.get('title', 'N/A')}")
    sections.append(f"**Description:** {bug.get('description', 'N/A')}")
    sections.append(f"**Reporter:** {bug.get('user_id', 'N/A')}")
    sections.append(f"**Device:** {bug.get('device_info', 'N/A')}")
    sections.append(f"**App Version:** {bug.get('app_version', 'N/A')}")
    sections.append(f"**Timestamp:** {bug.get('created_at', 'N/A')}")

    # Console logs -- may be long, truncate if needed
    console_logs = bug.get("console_logs", "N/A")
    if len(console_logs) > 1500:
        console_logs = console_logs[:1500] + "\n... (truncated)"
    sections.append(f"**Console Logs:**\n```\n{console_logs}\n```")

    # Steps to reproduce
    steps = bug.get("steps_to_reproduce", "N/A")
    sections.append(f"**Steps to Reproduce:** {steps}")

    return "\n\n".join(sections)
```

### HMAC Webhook Signature Validation
```python
# Source: Python stdlib hmac docs + webhook best practices
import hmac
import hashlib

def validate_webhook_signature(
    body: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Validate HMAC-SHA256 webhook signature.

    Args:
        body: Raw request body bytes
        signature_header: Value from X-Webhook-Signature header
        secret: Shared secret string

    Returns:
        True if signature is valid
    """
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header, expected)
```

### SQLite Schema for Bug Persistence
```python
# Source: aiosqlite docs + project requirements
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS bugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_id TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    title TEXT,
    description TEXT,
    user_id TEXT,
    device_info TEXT,
    app_version TEXT,
    console_logs TEXT,
    steps_to_reproduce TEXT,
    severity TEXT,
    raw_payload TEXT NOT NULL,
    message_id INTEGER,
    thread_id INTEGER,
    channel_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dismissed_at TEXT,
    dismissed_by TEXT
);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bug_id INTEGER NOT NULL REFERENCES bugs(id),
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT,
    changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bugs_hash_id ON bugs(hash_id);
CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);
CREATE INDEX IF NOT EXISTS idx_bugs_message_id ON bugs(message_id);
CREATE INDEX IF NOT EXISTS idx_status_history_bug_id ON status_history(bug_id);
"""

async def setup_database(db_path: str = "bugs.db") -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.executescript(SCHEMA)
    await db.commit()
    return db
```

### Short Hash ID Generation
```python
# Source: Python stdlib uuid/secrets
import secrets

async def generate_hash_id(db: aiosqlite.Connection, length: int = 4) -> str:
    """Generate a unique short hex hash ID.

    Uses 4 bytes (8 hex chars) for ~4 billion combinations.
    Checks DB for collisions before returning.
    """
    for _ in range(10):  # Max 10 attempts
        hash_id = secrets.token_hex(length)  # 4 bytes = 8 hex chars
        async with db.execute(
            "SELECT 1 FROM bugs WHERE hash_id = ?", (hash_id,)
        ) as cursor:
            if await cursor.fetchone() is None:
                return hash_id
    raise RuntimeError("Failed to generate unique hash ID after 10 attempts")
```

### Building the Button View for a Bug Report
```python
# Source: discord.py DynamicItem pattern
def build_bug_view(bug_id: str) -> discord.ui.View:
    """Build the action button view for a bug report.

    Analyze, Create Issue, and Draft Fix are disabled in Phase 1.
    Dismiss is active.
    """
    view = discord.ui.View(timeout=None)

    # Active button
    view.add_item(BugActionButton("dismiss", bug_id))

    # Disabled buttons (Phase 2-3 functionality)
    view.add_item(BugActionButton("analyze", bug_id, disabled=True))
    view.add_item(BugActionButton("create_issue", bug_id, disabled=True))
    view.add_item(BugActionButton("draft_fix", bug_id, disabled=True))

    return view
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Persistent Views with fixed custom_ids | DynamicItem with regex template | discord.py 2.4.0 (2024) | No DB lookup per button click; state encoded in custom_id |
| sqlite3 in asyncio (blocking) | aiosqlite with WAL mode | aiosqlite 0.22+ | Non-blocking DB access; concurrent reads during writes |
| web.run_app() for aiohttp | AppRunner + TCPSite | Always available | Non-blocking server alongside other async code |
| Manual cog loading | setup_hook with load_extension | discord.py 2.0+ | Clean async initialization before bot connects |

**Deprecated/outdated:**
- `before_invoke` / `after_invoke` for setup: Use `setup_hook()` instead
- `bot.loop.create_task()` in module-level setup: Use `cog_load()` async method
- Fixed persistent views per message: Use DynamicItem for scalable persistent buttons
- `commands.Bot(command_prefix=...)` with message_content intent: For button-only bots, message_content intent is unnecessary and may cause Discord to reject your bot verification

## Open Questions

1. **Supabase Edge Function Webhook Payload Schema**
   - What we know: The existing edge function sends bug reports to a Discord channel. The payload includes description, user ID, device info, timestamp, console logs (15-24 lines).
   - What's unclear: Exact field names, JSON structure, whether it includes severity, steps to reproduce, or app version. Also unclear: what header name the shared secret is sent in.
   - Recommendation: The user stated "payload structure to be provided before planning." The bot should accept any JSON structure and gracefully handle missing fields (per CONTEXT.md decisions). Define a normalization layer that maps incoming fields to the internal schema.

2. **Thread Auto-Archive Duration vs. Server Boost Level**
   - What we know: 7-day archive requires Level 2 boost, 3-day requires Level 1, 1-day is free. User requested "longest available."
   - What's unclear: The user's server boost level.
   - Recommendation: Check `guild.premium_tier` at runtime and use the highest available duration. The code example above implements this fallback. Note: the user requested 30 days, but Discord's maximum is 7 days with Level 2 boost. This should be communicated to the user.

3. **Webhook Signature Header Name**
   - What we know: HMAC-SHA256 with shared secret is the standard pattern.
   - What's unclear: The exact header name used by the Supabase edge function (could be `X-Webhook-Signature`, `Authorization`, or custom).
   - Recommendation: Make the header name configurable. Default to `X-Webhook-Signature`.

4. **Role Name for Button Gating**
   - What we know: CONTEXT.md specifies role-based gating (e.g., "Developer" role).
   - What's unclear: The exact role name on the user's server.
   - Recommendation: Make the role name configurable via environment variable. Default to "Developer".

## Discord Bot Intents

For this bot, the required intents are minimal:

```python
intents = discord.Intents.default()
# message_content is NOT needed -- we use interactions (buttons), not prefix commands
# members intent may be needed if we want to check role membership
# guilds intent is included in default()
```

**Important:** Do NOT enable `message_content` privileged intent. This bot uses button interactions and webhook ingestion only. Discord may reject your bot's verification if you request message_content without a valid use case for reading message content.

The `members` intent (privileged) may be needed for reliable role checking in `interaction_check`. However, `interaction.user.roles` is populated from the interaction payload itself, so it should work without the members intent for button interactions. Test this during development.

## Sources

### Primary (HIGH confidence)
- [discord.py PyPI](https://pypi.org/project/discord.py/) - Version 2.6.4, released Oct 8, 2025
- [discord.py persistent views example](https://github.com/Rapptz/discord.py/blob/master/examples/views/persistent.py) - DynamicItem implementation pattern
- [discord.py DynamicItem discussion](https://github.com/Rapptz/discord.py/discussions/9851) - Confirmed DynamicItem available since v2.4.0
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) - Version 0.22.1, released Dec 23, 2025
- [aiohttp PyPI](https://pypi.org/project/aiohttp/) - Version 3.13.3, released Jan 3, 2026
- [aiohttp web quickstart](https://docs.aiohttp.org/en/stable/web_quickstart.html) - AppRunner/TCPSite pattern
- [discord.py colour.py source](https://github.com/Rapptz/discord.py/blob/master/discord/colour.py) - Full named color list

### Secondary (MEDIUM confidence)
- [Persistent views tutorial](https://thegamecracks.github.io/discord.py/persistent_views.html) - Comprehensive guide with stateful examples (redirects to blog.thegamecracks.xyz)
- [aiohttp webhook server as Cog](https://gist.github.com/anshulxyz/437dc88597f661bb8f18570ab4f0d2bc) - Community pattern for running aiohttp alongside discord.py
- [Discord thread auto-archive guide](https://discord-media.com/en/news/stop-discord-threads-from-disappearing-the-ultimate-guide-to-auto-archive.html) - Boost level requirements for archive durations
- [Webhook HMAC validation](https://hookdeck.com/webhooks/guides/how-to-implement-sha256-webhook-signature-verification) - HMAC-SHA256 verification pattern
- [Supabase database webhooks docs](https://supabase.com/docs/guides/database/webhooks) - Payload structure for DB webhooks
- [Supabase edge functions docs](https://supabase.com/docs/guides/functions) - Edge function capabilities

### Tertiary (LOW confidence)
- Thread auto-archive duration boost requirements: Multiple sources agree (Level 2 for 7-day), but exact current Discord policy may have changed. Needs runtime verification via `guild.premium_tier`.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified on PyPI with current versions and release dates
- Architecture: HIGH - DynamicItem pattern verified from official discord.py examples; aiohttp AppRunner pattern confirmed by multiple sources
- Pitfalls: HIGH - Thread archive limits verified; embed limits well-documented; store-then-process is industry standard
- Webhook integration: MEDIUM - Supabase edge function payload schema is user-specific and not yet provided

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (30 days -- all libraries are stable release)
