"""AI analysis cog -- reaction tracking, priority override, and bug recovery."""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.embeds import build_summary_embed, build_analysis_embed

logger = logging.getLogger(__name__)


class AIAnalysisCog(commands.Cog):
    """Handles AI analysis events: thumbs-down feedback and priority override."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Reaction tracking (thumbs-down on analysis embeds)
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """Log thumbs-down reactions on analysis embeds for quality tracking."""
        # Only track thumbs-down reactions
        if payload.emoji.name not in ("\U0001f44e", "thumbsdown"):
            return

        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        # Look up if this message is an analysis embed
        bug = await self.bot.bug_repo.get_bug_by_analysis_message(
            payload.message_id
        )
        if bug is None:
            return

        logger.info(
            "Negative feedback on analysis for bug #%s by user %s",
            bug["hash_id"],
            payload.user_id,
        )

    # ------------------------------------------------------------------
    # Priority override slash command
    # ------------------------------------------------------------------

    @app_commands.command(
        name="set-priority",
        description="Override a bug's priority score",
    )
    @app_commands.describe(
        bug_id="The bug hash ID (e.g., a3f2b1c0)",
        priority="New priority level",
    )
    @app_commands.choices(
        priority=[
            app_commands.Choice(name="P1 - Critical", value="P1"),
            app_commands.Choice(name="P2 - High", value="P2"),
            app_commands.Choice(name="P3 - Medium", value="P3"),
            app_commands.Choice(name="P4 - Low", value="P4"),
        ]
    )
    async def set_priority(
        self,
        interaction: discord.Interaction,
        bug_id: str,
        priority: app_commands.Choice[str],
    ) -> None:
        """Manually override a bug's priority level."""
        await interaction.response.defer(ephemeral=True)

        # Role check (same as bug buttons -- require Developer role)
        role_name = self.bot.config.DEVELOPER_ROLE_NAME
        required_role = discord.utils.get(
            interaction.guild.roles, name=role_name
        )
        if required_role is None or required_role not in interaction.user.roles:
            await interaction.followup.send(
                f"You need the **{role_name}** role to override bug priority.",
                ephemeral=True,
            )
            return

        # Update priority in DB
        reasoning = f"Manual override by {interaction.user}"
        updated_bug = await self.bot.bug_repo.update_priority(
            bug_id, priority.value, reasoning, str(interaction.user)
        )

        if updated_bug is None:
            await interaction.followup.send(
                f"Bug **#{bug_id}** not found.", ephemeral=True
            )
            return

        # Update the channel embed if we can find it
        channel_id = updated_bug.get("channel_id")
        message_id = updated_bug.get("message_id")
        if channel_id and message_id:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel is not None:
                    msg = await channel.fetch_message(message_id)
                    from src.views.bug_buttons import build_bug_view

                    new_embed = build_summary_embed(updated_bug)
                    new_view = build_bug_view(bug_id, analyzed=True)
                    await msg.edit(embed=new_embed, view=new_view)
            except discord.HTTPException:
                logger.warning(
                    "Could not update channel embed for bug %s after priority override",
                    bug_id,
                )

        # Update the analysis embed in the thread if it exists
        analysis_msg_id = updated_bug.get("analysis_message_id")
        thread_id = updated_bug.get("thread_id")
        if analysis_msg_id and thread_id:
            try:
                thread = self.bot.get_channel(thread_id)
                if thread is None:
                    thread = await self.bot.fetch_channel(thread_id)
                if thread is not None:
                    analysis_msg = await thread.fetch_message(analysis_msg_id)
                    # Rebuild the analysis embed with updated priority
                    analysis_data = {
                        "root_cause": updated_bug.get("ai_root_cause", "N/A"),
                        "affected_area": updated_bug.get("ai_affected_area", "N/A"),
                        "severity": updated_bug.get("ai_severity", "medium"),
                        "suggested_fix": updated_bug.get("ai_suggested_fix", "N/A"),
                        "priority": updated_bug.get("priority", priority.value),
                        "priority_reasoning": updated_bug.get(
                            "priority_reasoning", reasoning
                        ),
                        "usage": {
                            "total_tokens": updated_bug.get("ai_tokens_used", 0)
                        },
                    }
                    new_analysis_embed = build_analysis_embed(
                        updated_bug, analysis_data
                    )
                    await analysis_msg.edit(embed=new_analysis_embed)
            except discord.HTTPException:
                logger.warning(
                    "Could not update analysis embed for bug %s after priority override",
                    bug_id,
                )

        await interaction.followup.send(
            f"Priority for #{bug_id} updated to **{priority.value}**",
            ephemeral=True,
        )
        logger.info(
            "Priority override for bug %s to %s by %s",
            bug_id,
            priority.value,
            interaction.user,
        )


    # ------------------------------------------------------------------
    # /recover-bug: re-create a bug record from an existing thread
    # ------------------------------------------------------------------

    @app_commands.command(
        name="recover-bug",
        description="Re-create a bug in the DB from an existing bug thread",
    )
    async def recover_bug(self, interaction: discord.Interaction) -> None:
        """Recover a bug record by parsing the thread's embed and detail message."""
        await interaction.response.defer(ephemeral=True)

        # Must be in a thread
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send(
                "Run this command inside a bug thread.", ephemeral=True
            )
            return

        thread = interaction.channel

        # Get the starter (parent) message with the summary embed
        try:
            starter = await thread.parent.fetch_message(thread.id)
        except discord.HTTPException:
            await interaction.followup.send(
                "Could not fetch the thread's starter message.",
                ephemeral=True,
            )
            return

        if not starter.embeds:
            await interaction.followup.send(
                "No embed found on the starter message.", ephemeral=True
            )
            return

        embed = starter.embeds[0]

        # Parse hash_id from embed title: "#hash_id — title" or "[DISMISSED] #hash_id — title"
        title_text = embed.title or ""
        match = re.search(r"#([a-f0-9]{8})", title_text)
        if not match:
            await interaction.followup.send(
                f"Could not parse bug hash from embed title: `{title_text}`",
                ephemeral=True,
            )
            return

        hash_id = match.group(1)

        # Check if already in DB
        existing = await self.bot.bug_repo.get_bug(hash_id)
        if existing is not None:
            await interaction.followup.send(
                f"Bug **#{hash_id}** already exists in the DB.", ephemeral=True
            )
            return

        # Extract fields from embed
        severity = None
        for field in embed.fields:
            if field.name == "Severity":
                severity = field.value.lower() if field.value else None

        # Parse the detail message (first message in thread) for description etc.
        description = None
        app_version = None
        steps = None
        reporter_name = None
        try:
            messages = [m async for m in thread.history(limit=5, oldest_first=True)]
            for msg in messages:
                if msg.author.id == self.bot.user.id and msg.content.startswith("## Bug Report"):
                    # Parse fields from detail text
                    text = msg.content
                    desc_match = re.search(
                        r"\*\*Description:\*\*\s*(.+?)(?:\n\n|\Z)", text, re.DOTALL
                    )
                    if desc_match:
                        description = desc_match.group(1).strip()
                    ver_match = re.search(r"\*\*App Version:\*\*\s*(.+)", text)
                    if ver_match and ver_match.group(1).strip() != "N/A":
                        app_version = ver_match.group(1).strip()
                    steps_match = re.search(
                        r"\*\*Steps to Reproduce:\*\*\s*(.+?)(?:\n\n|\Z)",
                        text,
                        re.DOTALL,
                    )
                    if steps_match:
                        steps = steps_match.group(1).strip()
                    rep_match = re.search(r"\*\*Reporter:\*\*\s*(.+)", text)
                    if rep_match and rep_match.group(1).strip() != "N/A":
                        reporter_name = rep_match.group(1).strip()
                    break
        except Exception as exc:
            logger.warning("Could not parse thread detail for recovery: %s", exc)

        # Create the bug in the DB
        raw_payload = {
            "title": None,
            "description": description,
            "severity": severity,
            "app_version": app_version,
            "steps_to_reproduce": steps,
            "reporter_name": reporter_name,
        }
        bug = await self.bot.bug_repo.create_bug(raw_payload, hash_id)

        # Update message refs so buttons work
        await self.bot.bug_repo.update_message_refs(
            hash_id, starter.id, thread.id, thread.parent_id
        )

        await interaction.followup.send(
            f"Bug **#{hash_id}** recovered. Buttons should work again.",
            ephemeral=True,
        )
        logger.info("Bug #%s recovered from thread by %s", hash_id, interaction.user)


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(AIAnalysisCog(bot))
