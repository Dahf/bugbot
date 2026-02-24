"""Database connection setup with schema creation."""

import os

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS bugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_id TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    title TEXT,
    description TEXT,
    user_id TEXT,
    reporter_name TEXT,
    device_info TEXT,
    app_version TEXT,
    console_logs TEXT,
    steps_to_reproduce TEXT,
    severity TEXT,
    screenshot_url TEXT,
    raw_payload TEXT NOT NULL,
    message_id INTEGER,
    thread_id INTEGER,
    channel_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dismissed_at TEXT,
    dismissed_by TEXT,
    priority TEXT,
    priority_reasoning TEXT,
    ai_root_cause TEXT,
    ai_affected_area TEXT,
    ai_severity TEXT,
    ai_suggested_fix TEXT,
    ai_tokens_used INTEGER,
    analysis_message_id INTEGER,
    analyzed_at TEXT,
    analyzed_by TEXT
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

CREATE TABLE IF NOT EXISTS github_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER UNIQUE NOT NULL,
    installation_id INTEGER NOT NULL,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_config_guild ON github_config(guild_id);
"""


_ANALYSIS_COLUMNS: list[tuple[str, str]] = [
    ("priority", "TEXT"),
    ("priority_reasoning", "TEXT"),
    ("ai_root_cause", "TEXT"),
    ("ai_affected_area", "TEXT"),
    ("ai_severity", "TEXT"),
    ("ai_suggested_fix", "TEXT"),
    ("ai_tokens_used", "INTEGER"),
    ("analysis_message_id", "INTEGER"),
    ("analyzed_at", "TEXT"),
    ("analyzed_by", "TEXT"),
]


async def migrate_add_analysis_columns(db: aiosqlite.Connection) -> None:
    """Add Phase 2 analysis columns to the bugs table if missing.

    This handles existing databases created with the Phase 1 schema.
    Idempotent -- safe to run multiple times.
    """
    async with db.execute("PRAGMA table_info(bugs)") as cursor:
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}

    for col_name, col_type in _ANALYSIS_COLUMNS:
        if col_name not in existing_columns:
            await db.execute(
                f"ALTER TABLE bugs ADD COLUMN {col_name} {col_type}"
            )

    await db.commit()


_GITHUB_COLUMNS: list[tuple[str, str]] = [
    ("github_issue_number", "INTEGER"),
    ("github_issue_url", "TEXT"),
    ("github_pr_number", "INTEGER"),
    ("github_pr_url", "TEXT"),
    ("github_branch_name", "TEXT"),
]


async def migrate_add_github_columns(db: aiosqlite.Connection) -> None:
    """Add Phase 3 GitHub columns to the bugs table if missing.

    This handles existing databases created with the Phase 1/2 schema.
    Idempotent -- safe to run multiple times.
    """
    async with db.execute("PRAGMA table_info(bugs)") as cursor:
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}

    for col_name, col_type in _GITHUB_COLUMNS:
        if col_name not in existing_columns:
            await db.execute(
                f"ALTER TABLE bugs ADD COLUMN {col_name} {col_type}"
            )

    await db.commit()


async def setup_database(db_path: str = "data/bugs.db") -> aiosqlite.Connection:
    """Create (or open) the SQLite database and ensure the schema exists.

    Enables WAL mode for concurrent read/write and foreign key enforcement.
    Creates the parent directory for *db_path* if it does not exist.
    """
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.executescript(SCHEMA)
    await db.commit()

    # Migrate existing databases to include Phase 2 analysis columns
    await migrate_add_analysis_columns(db)

    # Migrate existing databases to include Phase 3 GitHub columns
    await migrate_add_github_columns(db)

    return db


async def close_database(db: aiosqlite.Connection) -> None:
    """Commit any pending changes and close the database connection."""
    await db.commit()
    await db.close()
