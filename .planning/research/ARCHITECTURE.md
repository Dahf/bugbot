# Architecture Patterns

**Domain:** AI-powered Discord bot with webhook ingestion, GitHub automation, and Claude AI integration
**Researched:** 2026-02-23
**Confidence:** MEDIUM (training data only -- web search unavailable, patterns well-established but version details unverified)

## Recommended Architecture

**Pattern: Dual-Server Async Monolith with Service Layer**

A single Python process runs two concurrent async servers -- the discord.py bot gateway and a lightweight HTTP webhook listener (aiohttp) -- sharing an in-process service layer. This avoids the complexity of microservices while cleanly separating concerns.

```
                          +------------------+
                          |   Supabase Edge  |
                          |    Function      |
                          +--------+---------+
                                   |
                                   | POST /webhook/bug-report
                                   v
+-------------------+    +------------------+     +------------------+
|  Discord Gateway  |    |  HTTP Webhook    |     |  GitHub API      |
|  (discord.py)     |    |  Server (aiohttp)|     |  (githubkit)     |
|                   |    |                  |     |                  |
|  - Button clicks  |    |  - Bug reports   |     |  - Issues        |
|  - Thread mgmt    |    |  - Validates     |     |  - Branches      |
|  - Embed display  |    |    signatures    |     |  - PRs           |
+--------+----------+    +--------+---------+     +--------+---------+
         |                         |                        ^
         |                         |                        |
         v                         v                        |
+--------+-------------------------+------------------------+---------+
|                        Service Layer                                |
|                                                                     |
|  +----------------+  +------------------+  +---------------------+  |
|  | Bug Triage     |  | AI Analysis      |  | GitHub Automation   |  |
|  | Service        |  | Service          |  | Service             |  |
|  |                |  |                  |  |                     |  |
|  | - Dedup logic  |  | - Claude API     |  | - Issue creation    |  |
|  | - Priority     |  | - Prompt mgmt   |  | - Branch creation   |  |
|  | - Status mgmt  |  | - Code analysis  |  | - PR creation       |  |
|  +-------+--------+  +--------+---------+  +----------+----------+  |
|          |                     |                       |            |
|          +---------------------+-----------------------+            |
|                                |                                    |
|                    +-----------+-----------+                        |
|                    |   Data Layer          |                        |
|                    |   (SQLite + aiosqlite)|                        |
|                    |                       |                        |
|                    |   - Bug reports       |                        |
|                    |   - Thread mappings   |                        |
|                    |   - Dedup index       |                        |
|                    |   - Audit log         |                        |
|                    +-----------------------+                        |
+---------------------------------------------------------------------+
```

### Why a Monolith, Not Microservices

At "a few reports per week" volume for a solo-to-small-team, microservices add deployment complexity, inter-service communication overhead, and operational burden with zero benefit. A well-structured monolith with clear module boundaries can be split later if needed (it almost certainly will not be needed).

### Why Two Servers in One Process

discord.py runs its own async event loop connected to Discord's WebSocket gateway. The webhook listener needs its own HTTP server. Both are async Python, so they coexist naturally on the same event loop via `asyncio.gather()` or by embedding the HTTP server as a background task in the discord.py bot's startup. This is a well-established pattern in the discord.py ecosystem.

## Component Boundaries

| Component | Responsibility | Communicates With | Interface |
|-----------|---------------|-------------------|-----------|
| **Discord Bot** (discord.py) | Gateway connection, button/command handlers, thread management, embed rendering | Service Layer (calls into), Discord API (websocket + REST) | discord.py Cog classes |
| **Webhook Server** (aiohttp) | HTTP endpoint for Supabase, request validation, payload parsing | Service Layer (calls into), Supabase (receives from) | HTTP POST endpoints |
| **Bug Triage Service** | Deduplication, priority scoring, status state machine, bug lifecycle | AI Service (requests analysis), Data Layer (reads/writes) | Python async methods |
| **AI Analysis Service** | Claude API calls, prompt management, response parsing, code generation | Anthropic API (HTTP via anthropic SDK), Data Layer (reads context) | Python async methods |
| **GitHub Automation Service** | Issue CRUD, branch creation, file operations, PR creation | GitHub API (via githubkit async client), Data Layer (reads/writes) | Python async methods |
| **Data Layer** | Persistence, queries, migrations | SQLite via aiosqlite | Repository pattern classes |
| **Discord UI Layer** | Embeds, buttons, views, thread creation | Discord Bot (renders through) | discord.py View/Embed classes |

### Boundary Rules

1. **Discord Bot never calls GitHub or Claude directly.** It always goes through the service layer. This keeps Discord-specific code (embeds, buttons, threads) separate from business logic.
2. **Webhook Server never sends Discord messages directly.** It processes the incoming report through the service layer, which then uses a notification interface to post to Discord.
3. **Services never import discord.py types.** They return plain data objects (Pydantic models) that the Discord UI layer converts to embeds and views.
4. **Data Layer is the only component that touches SQLite.** Services use repository interfaces.

## Data Flow

### Flow 1: Bug Report Arrives (Primary Happy Path)

```
1. Supabase edge function POSTs JSON to /webhook/bug-report
2. Webhook Server validates signature/auth token
3. Webhook Server parses payload into BugReport Pydantic model
4. Bug Triage Service checks for duplicates (embedding similarity or field matching)
   - If duplicate: link to existing bug, update count, notify in existing thread
   - If new: continue
5. Bug Triage Service requests AI analysis from AI Analysis Service
6. AI Analysis Service calls Claude API with bug report + prompt
7. Claude returns: root cause hypothesis, affected area, severity estimate, suggested fix approach
8. Bug Triage Service computes priority score (AI severity + crash data + frequency)
9. Bug Triage Service persists bug report + analysis to Data Layer
10. Bug Triage Service emits "new_bug" event
11. Discord Bot receives event, creates embed with analysis summary
12. Discord Bot attaches button row: [Create Issue] [Draft Fix] [Dismiss] [View Details]
13. Discord Bot posts to configured bug-reports channel
```

### Flow 2: Developer Clicks "Create Issue"

```
1. Discord Bot receives button interaction
2. Discord Bot immediately defers the interaction (within 3 seconds)
3. Discord Bot calls Bug Triage Service.create_github_issue(bug_id)
4. Bug Triage Service retrieves bug + analysis from Data Layer
5. Bug Triage Service calls GitHub Automation Service.create_issue(structured_data)
6. GitHub Automation Service (via githubkit):
   a. Creates issue with title, body (from AI analysis), labels
   b. Returns issue URL and number
7. Bug Triage Service updates bug status to "issue_created", stores issue reference
8. Discord Bot creates a thread on the original message for this bug
9. Discord Bot updates embed with issue link, changes button states
10. Discord Bot posts issue link in thread via interaction followup
```

### Flow 3: Developer Clicks "Draft Fix"

```
1. Discord Bot receives button interaction
2. Discord Bot immediately defers the interaction (within 3 seconds)
3. Discord Bot sends "Working on it..." to the per-ticket thread
4. Bug Triage Service retrieves bug + analysis + relevant source files from Data Layer
5. AI Analysis Service:
   a. Fetches relevant files from GitHub via GitHub Automation Service (githubkit)
   b. Constructs prompt with bug report, analysis, and source code
   c. Calls Claude API (AsyncAnthropic) for code generation
   d. Returns proposed changes (file path + diff/content pairs)
6. Thread update: "Creating branch and PR..."
7. GitHub Automation Service (via githubkit):
   a. Creates branch: fix/bug-{id}-{short-description}
   b. Commits changed files
   c. Opens PR with AI-generated description, links to issue
   d. Returns PR URL
8. Bug Triage Service updates status to "pr_drafted"
9. Discord Bot updates embed and thread with PR link
10. Discord Bot posts summary of changes in thread
```

### Flow 4: Bug Dashboard Request

```
1. Developer clicks Dashboard button or uses admin command
2. Discord Bot calls Bug Triage Service.get_dashboard_data()
3. Bug Triage Service queries Data Layer for open bugs, statuses, assignments
4. Discord Bot renders dashboard embed with:
   - Open bugs grouped by priority
   - Status breakdown (new, triaged, issue_created, fix_drafted, resolved)
   - Recent activity
5. Discord Bot posts/updates dashboard embed
```

## Patterns to Follow

### Pattern 1: Cog-Based Bot Organization

**What:** discord.py's Cog system groups related commands, events, and listeners into classes that can be loaded/unloaded.

**When:** Always. Every logical grouping of Discord functionality should be a Cog.

**Why:** Keeps the bot entry point clean, enables hot-reloading during development, and naturally maps to feature boundaries.

```python
# cogs/triage.py
class TriageCog(commands.Cog):
    def __init__(self, bot: commands.Bot, triage_service: BugTriageService):
        self.bot = bot
        self.triage_service = triage_service

    @commands.Cog.listener()
    async def on_new_bug_report(self, bug: BugReport):
        channel = self.bot.get_channel(CONFIG.bug_channel_id)
        view = BugReportView(bug.id)
        await channel.send(embed=bug.to_embed(), view=view)
```

### Pattern 2: Dependency Injection via Bot Instance

**What:** Services are instantiated at startup and passed to Cogs via constructor. No global state.

**When:** Always. Every service dependency flows through constructors.

**Why:** Makes testing possible (mock services), makes dependencies explicit, avoids import-time side effects.

```python
# main.py
async def main():
    db = await Database.connect("data/bot.db")
    anthropic_client = anthropic.AsyncAnthropic()
    github_client = githubkit.GitHub(githubkit.TokenAuthStrategy(GITHUB_TOKEN))

    ai_service = AIAnalysisService(anthropic_client)
    github_service = GitHubAutomationService(github_client, REPO_OWNER, REPO_NAME)
    triage_service = BugTriageService(db, ai_service, github_service)

    bot = commands.Bot(command_prefix="!", intents=intents)
    await bot.add_cog(TriageCog(bot, triage_service))
    await bot.add_cog(DashboardCog(bot, triage_service))

    # Run bot + webhook server concurrently
    webhook_app = create_webhook_app(triage_service, bot)
    runner = aiohttp.web.AppRunner(webhook_app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    await bot.start(DISCORD_TOKEN)
```

### Pattern 3: Event Bus for Cross-Component Communication

**What:** Use discord.py's built-in `bot.dispatch()` to decouple the webhook server from Discord message sending.

**When:** When the webhook server needs to trigger Discord actions (posting a new bug report embed).

**Why:** The webhook server should not import discord.py types or hold a reference to specific channels. It publishes an event; the bot's listener picks it up and handles the Discord side.

```python
# In webhook handler:
bug = await triage_service.process_incoming_report(payload)
bot.dispatch("new_bug_report", bug)  # Custom event

# In Cog:
@commands.Cog.listener()
async def on_new_bug_report(self, bug: BugReport):
    channel = self.bot.get_channel(CONFIG.bug_channel_id)
    view = BugReportView(bug.id)
    await channel.send(embed=bug.to_embed(), view=view)
```

### Pattern 4: Persistent Views for Button Interactions

**What:** discord.py's `discord.ui.View` with `timeout=None` and `custom_id` on buttons, re-registered on bot restart.

**When:** For all button-based interactions on bug reports, since the bot may restart between when a message is posted and when a button is clicked.

**Why:** Default Views are lost on restart. Persistent Views with custom IDs survive restarts because they are re-registered in `setup_hook`.

```python
class BugReportView(discord.ui.View):
    def __init__(self, bug_id: str):
        super().__init__(timeout=None)
        self.bug_id = bug_id

    @discord.ui.button(label="Create Issue", style=discord.ButtonStyle.primary,
                       custom_id="bug_create_issue")
    async def create_issue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        # ... handle via service layer, post results to thread
```

### Pattern 5: Deferred Interactions for Long-Running Operations

**What:** Immediately defer Discord interactions, then use thread messages for progress updates.

**When:** Any button click that triggers an API call (AI analysis, GitHub operations).

**Why:** Discord interaction tokens expire after 15 minutes and must be acknowledged within 3 seconds. Long workflows (AI + GitHub = potentially minutes) should communicate via the per-ticket thread, not the interaction token.

```python
@discord.ui.button(label="Draft Fix", style=discord.ButtonStyle.danger,
                   custom_id="bug_draft_fix")
async def draft_fix(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.defer(thinking=True)
    thread = await self.get_or_create_thread(interaction.message)
    await thread.send("Analyzing bug and drafting fix...")

    try:
        result = await self.triage_service.draft_fix(self.bug_id)
        await thread.send(f"PR created: {result.pr_url}")
        await interaction.followup.send("Fix drafted! Check the thread for details.")
    except Exception as e:
        await thread.send(f"Error drafting fix: {e}")
```

### Pattern 6: Structured Configuration with Pydantic Settings

**What:** All configuration loaded into a typed Pydantic `BaseSettings` object at startup.

**When:** Always. No hardcoded values, no raw `os.environ` calls scattered through code.

**Why:** Single source of truth, validates at startup (fail fast), auto-loads from `.env`, type coercion built in.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    discord_token: str
    anthropic_api_key: str
    github_token: str
    github_repo_owner: str
    github_repo_name: str
    webhook_port: int = 8080
    webhook_secret: str
    bug_channel_id: int
    database_path: str = "data/bot.db"
    anthropic_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_file = ".env"
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous API Calls in Async Context

**What:** Using `requests` or synchronous GitHub/Claude clients inside async handlers.

**Why bad:** Blocks the entire event loop. Discord gateway heartbeats stop, the bot disconnects, webhook requests queue up and time out.

**Instead:** Use `anthropic.AsyncAnthropic` for Claude, `githubkit.GitHub` with async methods for GitHub. Every external API call must be `await`-ed through an async interface.

### Anti-Pattern 2: Business Logic in Button Callbacks

**What:** Putting GitHub API calls, Claude API calls, and database operations directly inside `discord.ui.Button` callback methods.

**Why bad:** Mixes Discord UI concerns with business logic. Impossible to test without mocking Discord. Cannot reuse logic from other entry points.

**Instead:** Button callbacks should call service methods and then update the Discord UI based on the result. The callback is a thin adapter.

### Anti-Pattern 3: Global Mutable State for Bug Tracking

**What:** Using module-level dictionaries or lists to track bugs, thread mappings, or processing state.

**Why bad:** Lost on restart, no concurrency safety, untestable, grows without bound.

**Instead:** SQLite database (via aiosqlite for async). Even at low volume, the data model is relational (bugs -> issues -> PRs -> threads) and needs to survive restarts.

### Anti-Pattern 4: One Giant bot.py File

**What:** All commands, event handlers, button callbacks, API integrations, and utility functions in a single file.

**Why bad:** Inevitable in quick prototypes, but rapidly becomes unmaintainable past ~300 lines. Merge conflicts if team grows. Cannot test individual features.

**Instead:** Cog-per-feature from day one. It costs nothing and pays dividends immediately.

### Anti-Pattern 5: Storing Secrets in Config Files

**What:** Putting API tokens in `config.json`, `settings.py`, or any tracked file.

**Why bad:** Secrets in git history. Even `.gitignore`-d config files get accidentally committed.

**Instead:** Environment variables (loaded from `.env` via pydantic-settings in dev, injected by Docker in prod). Never committed, never in config files.

## Data Model

### Core Entities

```
BugReport
  - id: UUID
  - external_id: str (from Supabase)
  - description: str
  - user_id: str
  - device_info: JSON
  - console_logs: str
  - timestamp: datetime
  - status: enum (new, analyzing, triaged, issue_created, fix_drafted, resolved, dismissed, duplicate)
  - priority: int (1-5)
  - ai_analysis: JSON (root cause, severity, affected area, fix approach)
  - duplicate_of: UUID (nullable, FK to BugReport)
  - discord_message_id: int
  - discord_thread_id: int (nullable)
  - github_issue_number: int (nullable)
  - github_pr_number: int (nullable)
  - assigned_to: str (nullable)
  - created_at: datetime
  - updated_at: datetime
```

### State Machine

```
new --> analyzing --> triaged --> issue_created --> fix_drafted --> resolved
  |                     |              |                |
  +---> dismissed       +-> dismissed  +-> dismissed    +-> dismissed
  |
  +---> duplicate (linked to existing)
```

## Scalability Considerations

| Concern | Current (few/week) | At 100/week | At 1000/week |
|---------|-------------------|-------------|--------------|
| Database | SQLite, single file | SQLite still fine | Consider PostgreSQL |
| Claude API | Sequential calls | Sequential still fine | Batch/queue with rate limiting |
| GitHub API | Direct calls | Direct calls fine | Rate limit awareness, queue |
| Discord messages | Direct sends | Direct sends fine | Rate limit handling (discord.py handles this) |
| Webhook server | Single aiohttp worker | Single worker fine | Still fine, add request queuing |
| Deduplication | Simple field matching | Embedding-based similarity | Vector DB (overkill until here) |

**Bottom line:** SQLite + single process handles the projected scale with significant headroom. Do not over-engineer for scale that may never arrive.

## Technology Choices Relevant to Architecture

| Decision | Choice | Architectural Implication |
|----------|--------|--------------------------|
| HTTP server | aiohttp | Runs on same event loop as discord.py natively (both use asyncio). Already a discord.py dependency. Lighter than FastAPI for 1-2 routes. |
| Database | SQLite + aiosqlite | Zero ops, file-based, async wrapper for non-blocking queries. Good enough for years at this volume. |
| GitHub client | githubkit (async) | Native async support avoids blocking the event loop. Typed models from OpenAPI spec prevent API mistakes. Handles auth, pagination, and rate limits. |
| Claude client | anthropic (official SDK) | The official `anthropic` Python SDK supports async natively via `AsyncAnthropic`. Use it directly -- no wrapper libraries needed. |
| Data models | Pydantic | Use at all external data boundaries (webhooks, API responses, config). Services return Pydantic models. Discord UI layer converts them to embeds. |

## Sources

- Architecture patterns based on training data knowledge of discord.py (v2.x), aiohttp, and Python async patterns (MEDIUM confidence -- well-established patterns but specific API details unverified against latest docs)
- discord.py Cog and Persistent View patterns are core framework features documented in discord.py official docs (MEDIUM confidence -- patterns stable since discord.py 2.0)
- GitHub REST API structure based on training data (HIGH confidence -- REST API is stable and well-documented)
- Anthropic Python SDK async support based on training data (MEDIUM confidence -- SDK exists but exact API may have evolved)
- githubkit documentation: https://github.com/yanyongyu/githubkit (MEDIUM confidence)
