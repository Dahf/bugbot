"""Developer notes cog -- @mention context notes in bug threads."""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.embeds import build_summary_embed
from src.views.bug_buttons import build_bug_view, _derive_bug_flags

logger = logging.getLogger(__name__)


class DeveloperNotesCog(commands.Cog):
    """Handles @mention developer context notes in bug threads.

    Listens for messages that mention the bot in bug threads, saves them as
    developer context notes, and provides /view-notes for retrieval.
    Also syncs edits and deletes via raw event listeners.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.notes_repo = bot.notes_repo

    # ------------------------------------------------------------------
    # Helper: strip bot mention from message content
    # ------------------------------------------------------------------

    def _strip_mention(self, content: str) -> str:
        """Remove bot mention from message content and strip whitespace."""
        bot_id = str(self.bot.user.id)
        # Remove both <@ID> and <@!ID> forms
        content = content.replace(f"<@{bot_id}>", "")
        content = content.replace(f"<@!{bot_id}>", "")
        return content.strip()

    # ------------------------------------------------------------------
    # on_message: save developer notes when bot is @mentioned in threads
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Save a developer context note when the bot is @mentioned in a bug thread."""
        # Skip bot messages
        if message.author.bot:
            return

        # Skip if bot not mentioned
        if self.bot.user not in message.mentions:
            return

        # Skip if not in a thread
        if not isinstance(message.channel, discord.Thread):
            return

        # Look up the bug for this thread
        bug = await self.bot.bug_repo.get_bug_by_thread_id(message.channel.id)
        if bug is None:
            return

        # Role check: require Developer role
        role_name = self.bot.config.DEVELOPER_ROLE_NAME
        required_role = discord.utils.get(message.guild.roles, name=role_name)
        if required_role is None or required_role not in message.author.roles:
            # Silently ignore non-developers
            return

        # Strip bot mention from content
        content = self._strip_mention(message.content)

        # Collect attachment URLs if any
        attachment_urls = None
        if message.attachments:
            import json
            attachment_urls = json.dumps([a.url for a in message.attachments])

        # If stripped content is empty and no attachments, show help
        if not content and not message.attachments:
            await message.reply(
                "Mention me with a message to add developer context for this bug. "
                "Example: `@BugBot I think this is caused by the auth token expiring`"
            )
            return

        # Save note
        await self.notes_repo.create_note(
            bug_id=bug["id"],
            discord_message_id=message.id,
            author_id=message.author.id,
            author_name=str(message.author),
            content=content,
            attachment_urls=attachment_urls,
        )

        # React with pencil emoji
        await message.add_reaction("\U0001f4dd")

        # Count notes for this bug
        note_count = await self.notes_repo.count_notes(bug["id"])

        # Reply with confirmation
        await message.reply(
            f"\U0001f4dd Context saved ({note_count} note{'s' if note_count != 1 else ''} for this bug)"
        )

        # Update summary embed with notes counter (non-fatal)
        try:
            channel_id = bug.get("channel_id")
            message_id = bug.get("message_id")
            if channel_id and message_id:
                channel = self.bot.get_channel(channel_id)
                if channel is not None:
                    msg = await channel.fetch_message(message_id)
                    new_embed = build_summary_embed(bug, note_count=note_count)
                    flags = _derive_bug_flags(bug)
                    new_view = build_bug_view(bug["hash_id"], **flags)
                    await msg.edit(embed=new_embed, view=new_view)
        except discord.HTTPException:
            logger.warning(
                "Could not update channel embed with notes counter for bug %s",
                bug["hash_id"],
            )

        logger.info(
            "Developer note saved for bug #%s by %s (note_count=%d)",
            bug["hash_id"],
            message.author,
            note_count,
        )

    # ------------------------------------------------------------------
    # on_raw_message_delete: remove note when Discord message is deleted
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        """Remove a stored note when its Discord message is deleted."""
        deleted = await self.notes_repo.delete_note_by_message_id(payload.message_id)
        if deleted:
            logger.info(
                "Developer note deleted (message_id=%s, channel_id=%s)",
                payload.message_id,
                payload.channel_id,
            )

    # ------------------------------------------------------------------
    # on_raw_message_edit: update note when Discord message is edited
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_message_edit(
        self, payload: discord.RawMessageUpdateEvent
    ) -> None:
        """Update a stored note when its Discord message is edited."""
        # Skip embed-only edits (no content change)
        if "content" not in payload.data:
            return

        new_content = self._strip_mention(payload.data["content"])
        updated = await self.notes_repo.update_note_by_message_id(
            payload.message_id, new_content
        )
        if updated:
            logger.info(
                "Developer note updated (message_id=%s)",
                payload.message_id,
            )

    # ------------------------------------------------------------------
    # /view-notes slash command
    # ------------------------------------------------------------------

    @app_commands.command(
        name="view-notes",
        description="View developer context notes for a bug",
    )
    @app_commands.describe(
        bug_id="The bug hash ID (e.g., a3f2b1c0)",
    )
    async def view_notes(
        self,
        interaction: discord.Interaction,
        bug_id: str,
    ) -> None:
        """Display all developer context notes for a bug."""
        await interaction.response.defer(ephemeral=True)

        # Fetch bug by hash_id
        bug = await self.bot.bug_repo.get_bug(bug_id)
        if bug is None:
            await interaction.followup.send(
                f"Bug **#{bug_id}** not found.", ephemeral=True
            )
            return

        # Fetch notes
        notes = await self.notes_repo.get_notes_for_bug(bug["id"])
        if not notes:
            await interaction.followup.send(
                f"No developer notes for bug **#{bug_id}**.", ephemeral=True
            )
            return

        # Build embed listing each note
        embed = discord.Embed(
            title=f"Developer Notes -- #{bug_id}",
            color=discord.Colour(0x3498DB),
        )

        for i, note in enumerate(notes, 1):
            # Truncate content to fit Discord embed field limits (1024 chars)
            content = note["content"]
            if len(content) > 1000:
                content = content[:997] + "..."

            timestamp = note.get("created_at", "Unknown")
            author = note.get("author_name", "Unknown")

            embed.add_field(
                name=f"#{i} by {author}",
                value=f"{content}\n*{timestamp}*",
                inline=False,
            )

        embed.set_footer(
            text=f"{len(notes)} note{'s' if len(notes) != 1 else ''} total"
        )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(DeveloperNotesCog(bot))
