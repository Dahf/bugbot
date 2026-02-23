# Technology Stack

**Project:** PreserveFood Discord Bot
**Researched:** 2026-02-23
**Note:** Web verification tools were unavailable during this research session. Versions are based on training data (cutoff early 2025). All version numbers should be verified against PyPI before `pip install`. Confidence levels reflect this limitation.

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12+ | Runtime | 3.12 has significant performance improvements (specializing interpreter), stable asyncio, and full library compatibility. 3.13 is available but some C-extension libraries may lag on support. Pin to 3.12.x for production stability. | MEDIUM |

### Core Framework

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| discord.py | >=2.3 | Discord bot framework | The dominant Python Discord library. Fully async, built-in support for buttons/views/modals (UI kit), slash commands, threads, webhooks, and embeds. Actively maintained again after the 2021 hiatus. Pycord and Nextcord forked during the hiatus but discord.py reclaimed the ecosystem — larger community, better docs, more examples. | MEDIUM |
| anthropic | >=0.39 | Claude API client | Official Anthropic Python SDK. Async support via `AsyncAnthropic`. Streaming, tool use, structured outputs. This is the only supported way to call Claude. | MEDIUM |
| aiohttp | >=3.9 | Webhook HTTP server | Already a transitive dependency of discord.py (it uses aiohttp internally). Running the Supabase webhook listener on aiohttp avoids adding a second HTTP framework. Lightweight, mature, async-native. Use `aiohttp.web` for the webhook server. | HIGH |

**Why aiohttp over FastAPI for webhooks:** FastAPI is excellent for building full REST APIs, but here we need a single webhook endpoint running inside the same async event loop as the Discord bot. aiohttp is already loaded by discord.py, shares the same event loop naturally, and avoids the overhead of uvicorn + Starlette + Pydantic for a single POST endpoint. FastAPI would be the right choice if this were a standalone API service.

### GitHub Integration

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| githubkit | >=0.11 | GitHub API client | Fully typed, async-native GitHub API client. Auto-generated from GitHub's OpenAPI spec so it covers 100% of the API surface including newer features. Supports both sync and async. PyGithub is more popular but is sync-only, which is a dealbreaker in an async Discord bot. githubkit avoids blocking the event loop when creating issues, branches, and PRs. | MEDIUM |

**Why githubkit over PyGithub:** PyGithub is the most well-known Python GitHub library but it is synchronous. In an async Discord bot, every PyGithub call would need `asyncio.to_thread()` wrapping, which is error-prone and scales poorly. githubkit provides native `async/await` support, full type hints, and is generated from GitHub's OpenAPI spec ensuring complete API coverage. The API surface is slightly more verbose but the async-native design is non-negotiable for this architecture.

**Why not raw httpx/aiohttp to GitHub API:** Building raw API calls works for 2-3 endpoints but this project needs issues, PRs, branches, file contents, and commit operations. A typed client prevents subtle API mistakes and handles pagination, rate limiting, and authentication consistently.

### Database / State

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| SQLite + aiosqlite | aiosqlite >=0.20 | Local state persistence | Tracks bug report dedup hashes, issue-to-thread mappings, PR status, and assignment state. SQLite is zero-infrastructure (single file), survives container restarts with a Docker volume, and handles this project's low write volume easily. aiosqlite wraps it for async access. No need for PostgreSQL/Redis at a few reports per week. | HIGH |

**Why not PostgreSQL:** Overkill for a single-bot, low-volume system. Adds a second container, connection management, and migration tooling. SQLite with a mounted volume is simpler and sufficient until the team is 5+ people or volume exceeds hundreds of reports/day.

**Why not Redis:** Redis is useful for caching and pub/sub but this bot has no caching needs and no multi-process communication. SQLite covers the state persistence requirement.

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| pydantic | >=2.5 | Data validation and models | Define structured types for bug reports, GitHub payloads, AI responses. Enforces schema at runtime. Use for all data boundaries (webhook input, API responses, config). | HIGH |
| python-dotenv | >=1.0 | Environment variable loading | Load `.env` file for local development. In production Docker uses real env vars, but dotenv keeps the dev experience clean. | HIGH |
| structlog | >=24.1 | Structured logging | JSON-formatted logs with context binding. Critical for debugging async bot behavior. Better than stdlib logging for correlation (attach thread_id, bug_id to all log entries in a flow). | MEDIUM |
| tenacity | >=8.2 | Retry logic | Retry failed API calls to GitHub/Claude with exponential backoff. Essential for production reliability. Both APIs have rate limits and transient failures. | HIGH |
| alembic | >=1.13 | Database migrations | Schema migrations for SQLite. Not needed immediately but add before the second schema change. Prevents manual ALTER TABLE mistakes. | MEDIUM |

### Development and Quality

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| pytest | >=8.0 | Testing framework | Unit and integration tests. Use pytest-asyncio for async test functions. | HIGH |
| pytest-asyncio | >=0.23 | Async test support | Test async Discord event handlers, GitHub API calls, webhook processing. | HIGH |
| ruff | >=0.4 | Linting and formatting | Replaces flake8 + black + isort in a single fast tool. Rust-based, sub-second on this project size. | HIGH |
| mypy | >=1.8 | Type checking | Catch type errors before runtime. Especially valuable with pydantic models and API client return types. | HIGH |
| pre-commit | >=3.6 | Git hooks | Run ruff + mypy on commit. Prevents broken code from reaching the repo. | MEDIUM |

### Docker and Deployment

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Docker | latest | Containerization | Single-container deployment. Python 3.12-slim base image. Multi-stage build to keep image small. | HIGH |
| docker-compose | >=2.24 | Local orchestration | Single-service compose file for local dev. Maps volume for SQLite persistence. Easy port mapping for webhook endpoint. | HIGH |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Discord library | discord.py | Pycord / Nextcord | Forked during discord.py's hiatus (2021-2022). discord.py resumed active development and reclaimed community momentum. Pycord diverged on API design. Nextcord stayed closer but has a smaller contributor base. Stick with the canonical library. |
| Discord library | discord.py | interactions.py | Focused exclusively on slash commands / application commands. Less mature for the full bot lifecycle (message events, threads, webhooks). |
| AI SDK | anthropic (official) | litellm / langchain | litellm is a proxy layer for multi-provider LLM calls — unnecessary complexity when committed to Claude. LangChain adds massive abstraction overhead for what amounts to a few API calls with structured prompts. Use the official SDK directly. |
| GitHub client | githubkit | PyGithub | Synchronous only. Would block the async event loop or require thread pool wrappers everywhere. |
| GitHub client | githubkit | gidgethub | Async-capable but lower-level (no auto-generated typed models). More manual JSON parsing. |
| Webhook server | aiohttp | FastAPI | FastAPI is a full web framework. We need one POST endpoint inside an existing async process. aiohttp is already a dependency and shares the event loop. |
| Webhook server | aiohttp | Quart | Flask-like async framework. Adds another dependency for a single endpoint. No advantage over aiohttp which is already present. |
| Database | SQLite + aiosqlite | PostgreSQL + asyncpg | Overkill. Adds infrastructure complexity (second container, connection pooling, migrations) for a system processing a few events per week. |
| Database | SQLite + aiosqlite | TinyDB / JSON files | No query capability, no ACID guarantees, corruption risk on concurrent writes. SQLite is barely more complex but vastly more reliable. |
| Task queue | None (in-process) | Celery / RQ / Dramatiq | At current volume (few reports/week), in-process async tasks are sufficient. A task queue adds Redis/RabbitMQ infrastructure. Revisit only if processing latency or volume demands it. |
| Logging | structlog | loguru | Loguru is pleasant for simple scripts but structlog's bound loggers and JSON output are better for production bot debugging where you need to correlate events across async handlers. |

## What NOT to Use

### LangChain / LlamaIndex
**Why not:** This project makes direct, well-defined API calls to Claude (analyze a bug report, draft a code fix). LangChain adds chains, agents, memory abstractions, and prompt templates that are unnecessary overhead. The anthropic SDK's tool use and structured output features cover everything needed. LangChain is appropriate for complex RAG pipelines or multi-step agent orchestration — not for a bot making 3-4 distinct API call patterns.

### Flask / Django
**Why not:** Synchronous web frameworks. The entire bot is async (discord.py requires it). Running Flask alongside would require a separate thread or process, complicating deployment and inter-process communication.

### MongoDB
**Why not:** Document databases are tempting for "flexible schemas" but bug reports have a well-defined structure (pydantic models). SQLite with proper schema is simpler to query, backup, and reason about.

### Cogs Framework (discord.py extension)
**Clarification:** discord.py Cogs are NOT something to avoid — they ARE the recommended way to organize bot commands and event handlers. Mentioned here because some tutorials skip them and put everything in a single file. Use Cogs from the start to separate concerns (webhook handling, bug triage, GitHub operations, dashboard).

## Project Structure

```
preservefooddiscordbot/
  bot/
    __init__.py
    main.py              # Bot entrypoint, loads cogs, starts webhook server
    config.py            # Pydantic Settings for env var loading
    cogs/
      __init__.py
      triage.py          # Bug report processing, AI analysis, dedup
      github.py          # Issue creation, PR creation, branch management
      dashboard.py       # Bug dashboard embed, status tracking
      admin.py           # Permissions, assignments, team management
    services/
      __init__.py
      claude.py          # Anthropic API wrapper with retry logic
      github_client.py   # githubkit wrapper with auth and common operations
      webhook.py         # aiohttp webhook server for Supabase
      database.py        # aiosqlite connection and query helpers
    models/
      __init__.py
      bug_report.py      # Pydantic models for bug data
      github_models.py   # Pydantic models for GH issue/PR payloads
    views/
      __init__.py
      report_view.py     # Discord Button views for bug report actions
      dashboard_view.py  # Dashboard embed builder
    utils/
      __init__.py
      dedup.py           # Similarity hashing for bug deduplication
      prompts.py         # Claude prompt templates
  tests/
    conftest.py
    test_triage.py
    test_github.py
    test_webhook.py
    test_dedup.py
  migrations/            # Alembic migrations (add when needed)
  Dockerfile
  docker-compose.yml
  pyproject.toml         # Project metadata + tool config (ruff, mypy, pytest)
  .env.example
  .gitignore
```

## Installation

```bash
# Create project with modern Python packaging
# pyproject.toml handles all dependency declaration

# Core dependencies
pip install "discord.py>=2.3" "anthropic>=0.39" "githubkit>=0.11" "aiosqlite>=0.20" "pydantic>=2.5" "python-dotenv>=1.0" "structlog>=24.1" "tenacity>=8.2"

# Dev dependencies
pip install -D "pytest>=8.0" "pytest-asyncio>=0.23" "ruff>=0.4" "mypy>=1.8" "pre-commit>=3.6"
```

```toml
# pyproject.toml (preferred over requirements.txt)
[project]
name = "preservefood-discord-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "discord.py>=2.3",
    "anthropic>=0.39",
    "githubkit>=0.11",
    "aiosqlite>=0.20",
    "pydantic>=2.5",
    "python-dotenv>=1.0",
    "structlog>=24.1",
    "tenacity>=8.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.8",
    "pre-commit>=3.6",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Docker Configuration

```dockerfile
# Dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first for layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY bot/ bot/

# Non-root user for security
RUN useradd --create-home botuser
USER botuser

CMD ["python", "-m", "bot.main"]
```

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - bot-data:/app/data  # SQLite persistence
    ports:
      - "8080:8080"  # Webhook listener
    restart: unless-stopped

volumes:
  bot-data:
```

## Environment Variables

```bash
# .env.example
DISCORD_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=your_server_id
BUG_CHANNEL_ID=channel_for_bug_reports

ANTHROPIC_API_KEY=your_anthropic_api_key
ANTHROPIC_MODEL=claude-sonnet-4-20250514

GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO_OWNER=your_github_username
GITHUB_REPO_NAME=your_repo_name

WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_SECRET=shared_secret_with_supabase

DATABASE_PATH=/app/data/bot.db
```

## Key Architecture Decisions in the Stack

### Single Process, Shared Event Loop
The Discord bot, webhook server, and all API calls run in one Python process sharing one asyncio event loop. This is correct for the volume (few events/week) and eliminates inter-process communication complexity. The aiohttp webhook server starts alongside the Discord bot using `discord.py`'s `setup_hook`.

### Pydantic as the Data Backbone
Every external data boundary uses a Pydantic model: incoming webhooks are validated, Claude responses are parsed into models, GitHub API payloads are structured. This catches malformed data at the boundary rather than deep in business logic.

### githubkit for Async GitHub Operations
Creating a branch, committing files, and opening a PR requires 4-6 sequential GitHub API calls. With PyGithub these would each block the event loop for 100-300ms. githubkit keeps them non-blocking, preserving bot responsiveness during the multi-step PR creation flow.

## Version Verification Checklist

**IMPORTANT:** Before installing, verify these versions against PyPI. My training data has a cutoff and newer versions may be available.

| Package | Verify At | Key Check |
|---------|-----------|-----------|
| discord.py | https://pypi.org/project/discord.py/ | v2.x still the stable line? |
| anthropic | https://pypi.org/project/anthropic/ | Check for breaking changes in latest |
| githubkit | https://pypi.org/project/githubkit/ | Still actively maintained? |
| aiosqlite | https://pypi.org/project/aiosqlite/ | Compatible with Python 3.12+? |
| pydantic | https://pypi.org/project/pydantic/ | v2.x still current? |

## Sources

- Training data knowledge (cutoff early 2025) for all recommendations
- discord.py documentation: https://discordpy.readthedocs.io/
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- githubkit: https://github.com/yanyongyu/githubkit
- aiosqlite: https://github.com/omnilib/aiosqlite
- Pydantic: https://docs.pydantic.dev/

**Confidence note:** All version numbers are MEDIUM confidence — they reflect the latest versions known from training data but could not be verified against live PyPI due to tool restrictions during this research session. The architectural recommendations (which library to use and why) are HIGH confidence as they reflect stable ecosystem patterns unlikely to shift in 6-12 months.
