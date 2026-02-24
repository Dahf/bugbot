"""Per-guild GitHub configuration CRUD operations."""

from datetime import datetime, timezone

import aiosqlite


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert an aiosqlite Row to a plain dict."""
    return dict(row)


class GitHubConfigRepository:
    """CRUD operations for per-guild GitHub App configuration."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        self.db.row_factory = aiosqlite.Row

    async def get_config(self, guild_id: int) -> dict | None:
        """Return the GitHub config for *guild_id*, or ``None`` if not set."""
        async with self.db.execute(
            "SELECT * FROM github_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    async def set_config(
        self,
        guild_id: int,
        installation_id: int,
        repo_owner: str,
        repo_name: str,
    ) -> dict:
        """Insert or replace the GitHub config for *guild_id*.

        Returns the stored config as a dict.
        """
        now = _utcnow_iso()
        await self.db.execute(
            """
            INSERT INTO github_config (
                guild_id, installation_id, repo_owner, repo_name,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                installation_id = excluded.installation_id,
                repo_owner = excluded.repo_owner,
                repo_name = excluded.repo_name,
                updated_at = excluded.updated_at
            """,
            (guild_id, installation_id, repo_owner, repo_name, now, now),
        )
        await self.db.commit()
        return await self.get_config(guild_id)  # type: ignore[return-value]

    async def delete_config(self, guild_id: int) -> bool:
        """Delete the GitHub config for *guild_id*.

        Returns ``True`` if a row was deleted, ``False`` if no config existed.
        """
        cursor = await self.db.execute(
            "DELETE FROM github_config WHERE guild_id = ?", (guild_id,)
        )
        await self.db.commit()
        return cursor.rowcount > 0
