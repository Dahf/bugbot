"""Bug report processing cog -- consumes the queue and posts to Discord."""

import asyncio
import logging

import discord
from discord.ext import commands

from src.config import Config
from src.utils.embeds import (
    build_summary_embed,
    build_thread_detail_message,
    get_auto_archive_duration,
    get_thread_name,
)

logger = logging.getLogger(__name__)


class BugReports(commands.Cog):
    """Processes queued bug reports and posts them to Discord.

    Consumes hash IDs from ``bot.processing_queue``, fetches the bug from
    the database, builds a summary embed with action buttons, sends it to
    the configured channel, creates a thread with full details, and stores
    the Discord message/thread references back in the database.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.process_task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        """Start the background queue consumer."""
        self.process_task = self.bot.loop.create_task(self.process_loop())
        logger.info("BugReports processing loop started")

    async def cog_unload(self) -> None:
        """Cancel the background queue consumer."""
        if self.process_task is not None:
            self.process_task.cancel()
            logger.info("BugReports processing loop cancelled")

    # ------------------------------------------------------------------
    # Queue consumer
    # ------------------------------------------------------------------

    async def process_loop(self) -> None:
        """Infinite loop that waits for bug IDs and processes them."""
        await self.bot.wait_until_ready()
        logger.info("BugReports process loop ready -- waiting for bugs")

        while True:
            hash_id: str = await self.bot.processing_queue.get()
            try:
                await self.process_bug_report(hash_id)
            except asyncio.CancelledError:
                raise  # Let cancellation propagate
            except Exception:
                logger.exception("Failed to process bug %s", hash_id)
            finally:
                self.bot.processing_queue.task_done()

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    async def process_bug_report(self, hash_id: str) -> None:
        """Fetch a bug from the DB, post embed + buttons, create thread."""
        # 1. Fetch bug from DB
        bug = await self.bot.bug_repo.get_bug(hash_id)
        if bug is None:
            logger.error("Bug %s not found in database -- skipping", hash_id)
            return

        # 2. Get the configured channel
        channel = self.bot.get_channel(self.bot.config.BUG_CHANNEL_ID)
        if channel is None:
            logger.error(
                "Bug channel %d not found -- is the bot in the correct server?",
                self.bot.config.BUG_CHANNEL_ID,
            )
            return

        # 3. Build summary embed
        embed = build_summary_embed(bug)

        # 4. Build button view (import here to avoid circular import at module level)
        from src.views.bug_buttons import build_bug_view

        view = build_bug_view(hash_id)

        # 5. Send embed + view to channel
        message = await channel.send(embed=embed, view=view)

        # 6. Create thread from the message
        thread: discord.Thread | None = None
        try:
            thread_name = get_thread_name(hash_id, bug)
            archive_duration = get_auto_archive_duration(channel.guild)
            thread = await message.create_thread(
                name=thread_name,
                auto_archive_duration=archive_duration,
            )
        except discord.HTTPException:
            logger.exception(
                "Failed to create thread for bug %s -- embed still posted",
                hash_id,
            )

        # 7. Post full details in thread
        if thread is not None:
            detail_message = build_thread_detail_message(bug)
            await thread.send(detail_message)

        # 8. Update DB with message/thread references
        thread_id = thread.id if thread is not None else 0
        await self.bot.bug_repo.update_message_refs(
            hash_id, message.id, thread_id, channel.id
        )

        logger.info(
            "Bug #%s posted to #%s with thread %s",
            hash_id,
            channel.name,
            thread_id if thread is not None else "(none)",
        )


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(BugReports(bot))
