"""AI analysis cog -- reaction tracking and priority override command."""

import logging

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


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(AIAnalysisCog(bot))
