"""Developer notes data model and CRUD operations."""

import json
from datetime import datetime, timezone

import aiosqlite


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert an aiosqlite Row to a plain dict."""
    return dict(row)


class DeveloperNotesRepository:
    """CRUD operations for developer context notes backed by aiosqlite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        # Enable dict-like row access (may already be set by BugRepository)
        self.db.row_factory = aiosqlite.Row

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_note(
        self,
        bug_id: int,
        discord_message_id: int,
        author_id: int,
        author_name: str,
        content: str,
        attachment_urls: str | None = None,
    ) -> dict:
        """Insert a new developer note and return it as a dict.

        *attachment_urls* should be a JSON array string of URLs, or None.
        """
        now = _utcnow_iso()

        # Serialize attachment_urls list to JSON string if provided as list
        if attachment_urls is not None and isinstance(attachment_urls, list):
            attachment_urls = json.dumps(attachment_urls)

        await self.db.execute(
            """
            INSERT INTO developer_notes (
                bug_id, discord_message_id, author_id, author_name,
                content, attachment_urls, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bug_id,
                discord_message_id,
                author_id,
                author_name,
                content,
                attachment_urls,
                now,
                now,
            ),
        )
        await self.db.commit()

        # Return the created note
        return await self.get_note_by_message_id(discord_message_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_notes_for_bug(self, bug_id: int) -> list[dict]:
        """Return all notes for a bug, ordered by created_at ASC."""
        async with self.db.execute(
            "SELECT * FROM developer_notes WHERE bug_id = ? ORDER BY created_at ASC",
            (bug_id,),
        ) as cursor:
            return [_row_to_dict(r) for r in await cursor.fetchall()]

    async def count_notes(self, bug_id: int) -> int:
        """Return the number of notes for a bug."""
        async with self.db.execute(
            "SELECT COUNT(*) FROM developer_notes WHERE bug_id = ?",
            (bug_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_note_by_message_id(self, message_id: int) -> dict | None:
        """Return a note by its Discord message ID, or None."""
        async with self.db.execute(
            "SELECT * FROM developer_notes WHERE discord_message_id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_note_by_message_id(
        self, message_id: int, new_content: str
    ) -> bool:
        """Update note content by Discord message ID.

        Returns True if a row was updated, False otherwise.
        """
        now = _utcnow_iso()
        cursor = await self.db.execute(
            """
            UPDATE developer_notes
            SET content = ?, updated_at = ?
            WHERE discord_message_id = ?
            """,
            (new_content, now, message_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_note_by_message_id(self, message_id: int) -> bool:
        """Delete a note by its Discord message ID.

        Returns True if a row was deleted, False otherwise.
        """
        cursor = await self.db.execute(
            "DELETE FROM developer_notes WHERE discord_message_id = ?",
            (message_id,),
        )
        await self.db.commit()
        return cursor.rowcount > 0
