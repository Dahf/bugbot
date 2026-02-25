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
        """Recover a bug record by parsing the thread's embed and detail message.

        Recovers: description, severity, app_version, steps, reporter,
        device_info, console_logs, AI analysis data, GitHub issue/PR links.
        """
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

        summary_embed = starter.embeds[0]

        # Parse hash_id from embed title: "#hash_id — title" or "[DISMISSED] #hash_id — title"
        title_text = summary_embed.title or ""
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

        # --- Parse summary embed fields ---
        embed_fields = {f.name: f.value for f in summary_embed.fields}
        severity = embed_fields.get("Severity", "").lower().strip() or None

        # GitHub issue link: "[#19](https://...)"
        github_issue_number = None
        github_issue_url = None
        gh_issue_val = embed_fields.get("GitHub Issue", "")
        gh_issue_match = re.search(r"\[#(\d+)\]\((https?://[^)]+)\)", gh_issue_val)
        if gh_issue_match:
            github_issue_number = int(gh_issue_match.group(1))
            github_issue_url = gh_issue_match.group(2)

        # PR link: "[PR #21](https://...)"
        github_pr_number = None
        github_pr_url = None
        gh_pr_val = embed_fields.get("Pull Request", "")
        gh_pr_match = re.search(r"\[PR #(\d+)\]\((https?://[^)]+)\)", gh_pr_val)
        if gh_pr_match:
            github_pr_number = int(gh_pr_match.group(1))
            github_pr_url = gh_pr_match.group(2)

        # Priority from embed
        priority = None
        priority_val = embed_fields.get("Priority", "")
        priority_match = re.search(r"\*\*(P[1-4])\*\*", priority_val)
        if priority_match:
            priority = priority_match.group(1)

        # --- Parse thread messages ---
        description = None
        app_version = None
        device_info = None
        steps = None
        reporter_name = None
        console_log_parts: list[str] = []
        analysis_data = {}
        analysis_message_id = None

        try:
            messages = [m async for m in thread.history(limit=50, oldest_first=True)]
            for msg in messages:
                if msg.author.id != self.bot.user.id:
                    continue

                # Detail message: "## Bug Report #hash_id"
                if msg.content.startswith("## Bug Report"):
                    text = msg.content
                    desc_match = re.search(
                        r"\*\*Description:\*\*\s*(.+?)(?:\n\n|\Z)", text, re.DOTALL
                    )
                    if desc_match:
                        description = desc_match.group(1).strip()
                    ver_match = re.search(r"\*\*App Version:\*\*\s*(.+)", text)
                    if ver_match and ver_match.group(1).strip() != "N/A":
                        app_version = ver_match.group(1).strip()
                    dev_match = re.search(r"\*\*Device:\*\*\s*(.+)", text)
                    if dev_match and dev_match.group(1).strip() != "N/A":
                        device_info = dev_match.group(1).strip()
                    steps_match = re.search(
                        r"\*\*Steps to Reproduce:\*\*\s*(.+?)(?:\n\n|\Z)",
                        text, re.DOTALL,
                    )
                    if steps_match:
                        steps = steps_match.group(1).strip()
                    rep_match = re.search(r"\*\*Reporter:\*\*\s*(.+)", text)
                    if rep_match and rep_match.group(1).strip() != "N/A":
                        reporter_name = rep_match.group(1).strip()

                # Console logs: may span multiple messages
                # "**Console Logs:**" or "**Console Logs (continued N/M):**"
                elif msg.content.startswith("**Console Logs"):
                    log_match = re.search(r"```\n?(.+?)\n?```", msg.content, re.DOTALL)
                    if log_match:
                        console_log_parts.append(log_match.group(1))

                # Analysis embed
                if msg.embeds:
                    for emb in msg.embeds:
                        if emb.title and "AI Analysis" in emb.title:
                            analysis_message_id = msg.id
                            afields = {f.name: f.value for f in emb.fields}
                            analysis_data = {
                                "root_cause": afields.get("Root Cause"),
                                "affected_area": afields.get("Affected Area"),
                                "severity": afields.get("Severity", "").lower().strip() or None,
                                "suggested_fix": afields.get("Suggested Fix"),
                            }
                            # Priority: "**P2** -- reasoning"
                            pri_val = afields.get("Priority", "")
                            pri_match = re.search(
                                r"\*\*(P[1-4])\*\*\s*--\s*(.+)", pri_val
                            )
                            if pri_match:
                                analysis_data["priority"] = pri_match.group(1)
                                analysis_data["priority_reasoning"] = pri_match.group(2).strip()
        except Exception as exc:
            logger.warning("Could not fully parse thread for recovery: %s", exc)

        # --- Combine console log parts ---
        console_logs_raw = "\n".join(console_log_parts) if console_log_parts else None

        # --- Create the bug in the DB ---
        raw_payload = {
            "title": None,
            "description": description,
            "severity": severity,
            "app_version": app_version,
            "steps_to_reproduce": steps,
            "reporter_name": reporter_name,
            "device_info": device_info,
            "console_logs": console_logs_raw,
        }
        bug = await self.bot.bug_repo.create_bug(raw_payload, hash_id)

        # Update message refs so buttons work
        await self.bot.bug_repo.update_message_refs(
            hash_id, starter.id, thread.id, thread.parent_id
        )

        # Store analysis data if found
        recovered_parts = ["description", "message refs"]
        if analysis_data.get("root_cause"):
            analysis_data.setdefault("priority", priority or "P3")
            analysis_data.setdefault("priority_reasoning", "Recovered from thread")
            analysis_data["usage"] = {"total_tokens": 0}
            await self.bot.bug_repo.store_analysis(
                hash_id, analysis_data, "recovery"
            )
            recovered_parts.append("AI analysis")
            if analysis_message_id:
                await self.bot.bug_repo.store_analysis_message_id(
                    hash_id, analysis_message_id
                )

        # Store GitHub issue if found
        if github_issue_number:
            await self.bot.bug_repo.store_github_issue(
                hash_id, github_issue_number, github_issue_url, "recovery"
            )
            recovered_parts.append(f"GitHub issue #{github_issue_number}")

        # Store GitHub PR if found
        if github_pr_number:
            await self.bot.bug_repo.store_github_pr(
                hash_id, github_pr_number, github_pr_url, "recovery"
            )
            recovered_parts.append(f"PR #{github_pr_number}")

        if console_logs_raw:
            recovered_parts.append("console logs")

        parts_str = ", ".join(recovered_parts)
        await interaction.followup.send(
            f"Bug **#{hash_id}** recovered: {parts_str}.\n"
            "Buttons should work again.",
            ephemeral=True,
        )
        logger.info("Bug #%s recovered from thread by %s", hash_id, interaction.user)

    # ------------------------------------------------------------------
    # /reset-buttons: refresh buttons on an existing bug embed
    # ------------------------------------------------------------------

    @app_commands.command(
        name="reset-buttons",
        description="Refresh the buttons on a bug embed (optionally clear issue/fix/analysis)",
    )
    @app_commands.describe(
        clear="Optionally clear a field group so its button becomes active again",
    )
    @app_commands.choices(
        clear=[
            app_commands.Choice(name="None -- just refresh", value="none"),
            app_commands.Choice(name="Issue -- re-enable Create Issue", value="issue"),
            app_commands.Choice(name="Fix -- re-enable Draft Fix", value="fix"),
            app_commands.Choice(name="Analysis -- re-enable Analyze", value="analysis"),
        ]
    )
    async def reset_buttons(
        self,
        interaction: discord.Interaction,
        clear: app_commands.Choice[str] | None = None,
    ) -> None:
        """Re-derive button states from the DB and update the starter embed.

        When *clear* is provided, the corresponding DB fields are NULLed
        out first so the associated button becomes active again.
        """
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

        # Parse hash_id from embed title
        title_text = starter.embeds[0].title or ""
        match = re.search(r"#([a-f0-9]{8})", title_text)
        if not match:
            await interaction.followup.send(
                f"Could not parse bug hash from embed title: `{title_text}`",
                ephemeral=True,
            )
            return

        hash_id = match.group(1)

        # Look up the bug in the DB
        bug = await self.bot.bug_repo.get_bug(hash_id)
        if bug is None:
            await interaction.followup.send(
                f"Bug **#{hash_id}** not found in the DB. "
                "Run `/recover-bug` first to restore it.",
                ephemeral=True,
            )
            return

        # Clear fields if requested
        clear_value = clear.value if clear else "none"
        cleared_label = ""
        if clear_value != "none":
            bug = await self.bot.bug_repo.clear_fields(
                hash_id, clear_value, str(interaction.user)
            )
            cleared_label = f" (cleared **{clear_value}**)"

        # Rebuild embed and buttons from current DB state
        from src.views.bug_buttons import build_bug_view, _derive_bug_flags

        note_count = None
        if hasattr(self.bot, "notes_repo"):
            note_count = await self.bot.notes_repo.count_notes(bug["id"])

        new_embed = build_summary_embed(bug, note_count=note_count)
        flags = _derive_bug_flags(bug)
        new_view = build_bug_view(hash_id, **flags)

        try:
            await starter.edit(embed=new_embed, view=new_view)
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Failed to update the embed: {exc}", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"Buttons for **#{hash_id}** refreshed{cleared_label}.",
            ephemeral=True,
        )
        logger.info(
            "Buttons reset for bug #%s (clear=%s) by %s",
            hash_id, clear_value, interaction.user,
        )


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(AIAnalysisCog(bot))
