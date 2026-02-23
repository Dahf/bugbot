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
    return db


async def close_database(db: aiosqlite.Connection) -> None:
    """Commit any pending changes and close the database connection."""
    await db.commit()
    await db.close()
