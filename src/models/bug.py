"""Bug data model and CRUD operations."""

import json
from datetime import datetime, timezone

import aiosqlite

from src.utils.hashing import generate_hash_id

VALID_STATUSES = (
    "received",
    "analyzing",
    "triaged",
    "issue_created",
    "fix_drafted",
    "resolved",
    "dismissed",
)


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert an aiosqlite Row to a plain dict."""
    return dict(row)


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class BugRepository:
    """CRUD operations for bug reports backed by aiosqlite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        # Enable dict-like row access
        self.db.row_factory = aiosqlite.Row

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_bug(self, raw_payload: dict, hash_id: str) -> dict:
        """Insert a new bug from a webhook payload and return it as a dict.

        Extracts known fields from *raw_payload* with ``.get()`` (defaulting
        to ``None``).  Structured fields (device_info, console_logs) are
        serialized to JSON strings for storage.  Stores the full payload as a
        JSON string.  Inserts an initial ``status_history`` entry
        (old_status=None, new_status='received').
        """
        now = _utcnow_iso()
        raw_json = json.dumps(raw_payload)

        # Serialize structured fields to JSON strings for TEXT columns
        device_info = raw_payload.get("device_info")
        if device_info is not None and not isinstance(device_info, str):
            device_info = json.dumps(device_info)

        console_logs = raw_payload.get("console_logs")
        if console_logs is not None and not isinstance(console_logs, str):
            console_logs = json.dumps(console_logs)

        await self.db.execute(
            """
            INSERT INTO bugs (
                hash_id, status, title, description, user_id,
                reporter_name, device_info, app_version, console_logs,
                steps_to_reproduce, severity, screenshot_url,
                raw_payload, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hash_id,
                "received",
                raw_payload.get("title"),
                raw_payload.get("description"),
                raw_payload.get("user_id"),
                raw_payload.get("reporter_name"),
                device_info,
                raw_payload.get("app_version"),
                console_logs,
                raw_payload.get("steps_to_reproduce"),
                raw_payload.get("severity"),
                raw_payload.get("screenshot_url"),
                raw_json,
                now,
                now,
            ),
        )

        # Fetch the auto-incremented id for the status_history foreign key
        async with self.db.execute(
            "SELECT id FROM bugs WHERE hash_id = ?", (hash_id,)
        ) as cursor:
            row = await cursor.fetchone()
            bug_id = row["id"]

        await self.db.execute(
            """
            INSERT INTO status_history (bug_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bug_id, None, "received", None, now),
        )

        await self.db.commit()
        return await self.get_bug(hash_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_bug(self, hash_id: str) -> dict | None:
        """Return a single bug by *hash_id*, or ``None`` if not found."""
        async with self.db.execute(
            "SELECT * FROM bugs WHERE hash_id = ?", (hash_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    async def get_bug_by_thread_id(self, thread_id: int) -> dict | None:
        """Return a bug by its Discord thread_id, or None."""
        async with self.db.execute(
            "SELECT * FROM bugs WHERE thread_id = ?", (thread_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    async def get_bug_by_analysis_message(self, message_id: int) -> dict | None:
        """Return a bug by its analysis embed *message_id*, or ``None``."""
        async with self.db.execute(
            "SELECT * FROM bugs WHERE analysis_message_id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    async def list_bugs(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        """List bugs, optionally filtered by *status*."""
        if status is not None:
            async with self.db.execute(
                "SELECT * FROM bugs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ) as cursor:
                return [_row_to_dict(r) for r in await cursor.fetchall()]
        else:
            async with self.db.execute(
                "SELECT * FROM bugs ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cursor:
                return [_row_to_dict(r) for r in await cursor.fetchall()]

    async def get_status_history(self, hash_id: str) -> list[dict]:
        """Return the full status history for a bug identified by *hash_id*."""
        async with self.db.execute(
            """
            SELECT sh.* FROM status_history sh
            JOIN bugs b ON b.id = sh.bug_id
            WHERE b.hash_id = ?
            ORDER BY sh.changed_at ASC
            """,
            (hash_id,),
        ) as cursor:
            return [_row_to_dict(r) for r in await cursor.fetchall()]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_status(
        self, hash_id: str, new_status: str, changed_by: str | None = None
    ) -> dict | None:
        """Update a bug's status and record the change in status_history.

        Returns the updated bug dict, or ``None`` if *hash_id* not found.
        Raises ``ValueError`` if *new_status* is not in ``VALID_STATUSES``.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{new_status}'. Must be one of: {VALID_STATUSES}"
            )

        bug = await self.get_bug(hash_id)
        if bug is None:
            return None

        now = _utcnow_iso()
        old_status = bug["status"]

        await self.db.execute(
            "UPDATE bugs SET status = ?, updated_at = ? WHERE hash_id = ?",
            (new_status, now, hash_id),
        )
        await self.db.execute(
            """
            INSERT INTO status_history (bug_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bug["id"], old_status, new_status, changed_by, now),
        )
        await self.db.commit()
        return await self.get_bug(hash_id)

    async def update_message_refs(
        self, hash_id: str, message_id: int, thread_id: int, channel_id: int
    ) -> None:
        """Update Discord message/thread/channel references after posting."""
        now = _utcnow_iso()
        await self.db.execute(
            """
            UPDATE bugs
            SET message_id = ?, thread_id = ?, channel_id = ?, updated_at = ?
            WHERE hash_id = ?
            """,
            (message_id, thread_id, channel_id, now, hash_id),
        )
        await self.db.commit()

    async def mark_dismissed(
        self, hash_id: str, dismissed_by: str
    ) -> dict | None:
        """Set a bug's status to 'dismissed' with timestamp and attribution.

        Returns the updated bug dict, or ``None`` if *hash_id* not found.
        """
        bug = await self.get_bug(hash_id)
        if bug is None:
            return None

        now = _utcnow_iso()
        old_status = bug["status"]

        await self.db.execute(
            """
            UPDATE bugs
            SET status = 'dismissed', dismissed_at = ?, dismissed_by = ?, updated_at = ?
            WHERE hash_id = ?
            """,
            (now, dismissed_by, now, hash_id),
        )
        await self.db.execute(
            """
            INSERT INTO status_history (bug_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bug["id"], old_status, "dismissed", dismissed_by, now),
        )
        await self.db.commit()
        return await self.get_bug(hash_id)

    # ------------------------------------------------------------------
    # AI Analysis
    # ------------------------------------------------------------------

    async def store_analysis(
        self, hash_id: str, analysis: dict, analyzed_by: str
    ) -> dict | None:
        """Store AI analysis results for a bug and transition status to 'triaged'.

        *analysis* must contain keys: root_cause, affected_area, severity,
        suggested_fix, priority, priority_reasoning, and usage.total_tokens.

        Returns the updated bug dict, or ``None`` if *hash_id* not found.
        """
        bug = await self.get_bug(hash_id)
        if bug is None:
            return None

        now = _utcnow_iso()
        old_status = bug["status"]

        await self.db.execute(
            """
            UPDATE bugs
            SET priority = ?,
                priority_reasoning = ?,
                ai_root_cause = ?,
                ai_affected_area = ?,
                ai_severity = ?,
                ai_suggested_fix = ?,
                ai_tokens_used = ?,
                analyzed_at = ?,
                analyzed_by = ?,
                status = 'triaged',
                updated_at = ?
            WHERE hash_id = ?
            """,
            (
                analysis["priority"],
                analysis["priority_reasoning"],
                analysis["root_cause"],
                analysis["affected_area"],
                analysis["severity"],
                analysis["suggested_fix"],
                analysis["usage"]["total_tokens"],
                now,
                analyzed_by,
                now,
                hash_id,
            ),
        )
        await self.db.execute(
            """
            INSERT INTO status_history (bug_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bug["id"], old_status, "triaged", analyzed_by, now),
        )
        await self.db.commit()
        return await self.get_bug(hash_id)

    async def store_analysis_message_id(
        self, hash_id: str, message_id: int
    ) -> None:
        """Store the Discord message ID of the analysis embed."""
        now = _utcnow_iso()
        await self.db.execute(
            "UPDATE bugs SET analysis_message_id = ?, updated_at = ? WHERE hash_id = ?",
            (message_id, now, hash_id),
        )
        await self.db.commit()

    async def update_priority(
        self, hash_id: str, priority: str, reasoning: str, changed_by: str
    ) -> dict | None:
        """Manually override the priority and reasoning for a bug.

        Does NOT change the bug's status -- this is a priority-only update.
        Returns the updated bug dict, or ``None`` if *hash_id* not found.
        """
        bug = await self.get_bug(hash_id)
        if bug is None:
            return None

        now = _utcnow_iso()
        await self.db.execute(
            """
            UPDATE bugs
            SET priority = ?, priority_reasoning = ?, updated_at = ?
            WHERE hash_id = ?
            """,
            (priority, reasoning, now, hash_id),
        )
        await self.db.commit()
        return await self.get_bug(hash_id)

    # ------------------------------------------------------------------
    # GitHub Issue
    # ------------------------------------------------------------------

    async def store_github_issue(
        self, hash_id: str, issue_number: int, issue_url: str, changed_by: str
    ) -> dict | None:
        """Store GitHub issue details and transition status to 'issue_created'.

        Returns the updated bug dict, or ``None`` if *hash_id* not found.
        """
        bug = await self.get_bug(hash_id)
        if bug is None:
            return None

        now = _utcnow_iso()
        old_status = bug["status"]

        await self.db.execute(
            """
            UPDATE bugs
            SET github_issue_number = ?,
                github_issue_url = ?,
                status = 'issue_created',
                updated_at = ?
            WHERE hash_id = ?
            """,
            (issue_number, issue_url, now, hash_id),
        )
        await self.db.execute(
            """
            INSERT INTO status_history (bug_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bug["id"], old_status, "issue_created", changed_by, now),
        )
        await self.db.commit()
        return await self.get_bug(hash_id)

    # ------------------------------------------------------------------
    # GitHub PR
    # ------------------------------------------------------------------

    async def store_github_pr(
        self,
        hash_id: str,
        pr_number: int,
        pr_url: str,
        branch_name: str,
        changed_by: str,
    ) -> dict | None:
        """Store GitHub PR details and transition status to 'fix_drafted'.

        Returns the updated bug dict, or ``None`` if *hash_id* not found.
        """
        bug = await self.get_bug(hash_id)
        if bug is None:
            return None

        now = _utcnow_iso()
        old_status = bug["status"]

        await self.db.execute(
            """
            UPDATE bugs
            SET github_pr_number = ?,
                github_pr_url = ?,
                github_branch_name = ?,
                status = 'fix_drafted',
                updated_at = ?
            WHERE hash_id = ?
            """,
            (pr_number, pr_url, branch_name, now, hash_id),
        )
        await self.db.execute(
            """
            INSERT INTO status_history (bug_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bug["id"], old_status, "fix_drafted", changed_by, now),
        )
        await self.db.commit()
        return await self.get_bug(hash_id)

    async def get_bug_by_github_issue(
        self, issue_number: int
    ) -> dict | None:
        """Return a bug by its GitHub *issue_number*, or ``None``."""
        async with self.db.execute(
            "SELECT * FROM bugs WHERE github_issue_number = ?",
            (issue_number,),
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    async def get_bug_by_branch_name(
        self, branch_name: str
    ) -> dict | None:
        """Return a bug by its GitHub *branch_name*, or ``None``."""
        async with self.db.execute(
            "SELECT * FROM bugs WHERE github_branch_name = ?",
            (branch_name,),
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Store-then-process entry point
    # ------------------------------------------------------------------

    async def store_raw_report(self, payload: dict) -> str:
        """Store a raw webhook payload immediately and return the hash_id.

        This is called by the webhook handler *before* any further processing
        to guarantee the report is persisted even if later steps fail.
        """
        hash_id = await generate_hash_id(self.db)
        await self.create_bug(payload, hash_id)
        return hash_id
