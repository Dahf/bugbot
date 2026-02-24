"""Persistent DynamicItem buttons for bug report actions."""

import logging
import re

import anthropic
import discord

from src.utils.embeds import build_summary_embed, build_analysis_embed, _get_display_title
from src.utils.github_templates import (
    build_issue_body,
    get_priority_label,
    get_area_label,
    get_bot_label,
)

logger = logging.getLogger(__name__)

# Action metadata ---------------------------------------------------------

_LABEL_MAP = {
    "dismiss": "Dismiss",
    "analyze": "Analyze",
    "create_issue": "Create Issue",
    "draft_fix": "Draft Fix",
}

_EMOJI_MAP = {
    "dismiss": "\U0001f5d1",       # Wastebasket
    "analyze": "\U0001f50d",       # Magnifying glass
    "create_issue": "\U0001f4cb",  # Clipboard
    "draft_fix": "\U0001f527",     # Wrench
}

# Active styles per action (used when the button is enabled)
_ACTIVE_STYLE_MAP = {
    "dismiss": discord.ButtonStyle.danger,    # Red
    "analyze": discord.ButtonStyle.primary,   # Blurple
    "create_issue": discord.ButtonStyle.primary,
    "draft_fix": discord.ButtonStyle.primary,
}


# -------------------------------------------------------------------------
# DynamicItem button
# -------------------------------------------------------------------------

class BugActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"bug:(?P<action>\w+):(?P<bug_id>[a-f0-9]+)",
):
    """A persistent button that encodes the action type and bug hash ID.

    Custom ID format: ``bug:<action>:<bug_id>``
    Example: ``bug:dismiss:a3f2b1c0``

    Registered via ``bot.add_dynamic_items(BugActionButton)`` in setup_hook
    so that buttons survive bot restarts (FOUND-06).
    """

    def __init__(
        self, action: str, bug_id: str, *, disabled: bool = False
    ) -> None:
        # When disabled, use secondary (grey) style; otherwise the action's style
        style = (
            discord.ButtonStyle.secondary
            if disabled
            else _ACTIVE_STYLE_MAP.get(action, discord.ButtonStyle.primary)
        )
        super().__init__(
            discord.ui.Button(
                label=_LABEL_MAP.get(action, action.replace("_", " ").title()),
                style=style,
                emoji=_EMOJI_MAP.get(action),
                custom_id=f"bug:{action}:{bug_id}",
                disabled=disabled,
            )
        )
        self.action = action
        self.bug_id = bug_id

    # -- DynamicItem protocol ------------------------------------------------

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        """Reconstruct the button from a custom_id regex match."""
        action = match["action"]
        bug_id = match["bug_id"]
        return cls(action, bug_id)

    # -- Role gating ----------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure the user has the required role before handling the click."""
        role_name = interaction.client.config.DEVELOPER_ROLE_NAME
        required_role = discord.utils.get(
            interaction.guild.roles, name=role_name
        )
        if required_role is None or required_role not in interaction.user.roles:
            await interaction.response.send_message(
                f"You need the **{role_name}** role to interact with bug reports.",
                ephemeral=True,
            )
            return False
        return True

    # -- Callback dispatch ----------------------------------------------------

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle button clicks -- dispatch by action type."""
        if self.action == "dismiss":
            await self._handle_dismiss(interaction)
        elif self.action == "analyze":
            await self._handle_analyze(interaction)
        elif self.action == "create_issue":
            await self._handle_create_issue(interaction)
        elif self.action == "draft_fix":
            label = _LABEL_MAP.get(self.action, self.action)
            await interaction.response.send_message(
                f"The **{label}** feature is coming in a future update.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Unknown action.", ephemeral=True
            )

    # -- Dismiss handler -------------------------------------------------------

    async def _handle_dismiss(self, interaction: discord.Interaction) -> None:
        """Mark the bug as dismissed and update the embed + buttons."""
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client
        updated_bug = await bot.bug_repo.mark_dismissed(
            self.bug_id, str(interaction.user)
        )

        if updated_bug is None:
            await interaction.followup.send(
                f"Bug **#{self.bug_id}** not found.", ephemeral=True
            )
            return

        # Rebuild embed with dismissed styling (grey colour, [DISMISSED] prefix)
        new_embed = build_summary_embed(updated_bug)

        # Rebuild view with Dismiss now disabled
        new_view = build_bug_view(self.bug_id, dismissed=True)

        # Edit the original message in the channel
        await interaction.message.edit(embed=new_embed, view=new_view)

        # Post confirmation in the thread (if one exists)
        if interaction.message.thread is not None:
            try:
                await interaction.message.thread.send(
                    f"Bug **#{self.bug_id}** dismissed by {interaction.user.mention}."
                )
            except discord.HTTPException:
                logger.warning(
                    "Could not post dismiss confirmation in thread for bug %s",
                    self.bug_id,
                )

        await interaction.followup.send(
            f"Bug **#{self.bug_id}** has been dismissed.", ephemeral=True
        )
        logger.info(
            "Bug %s dismissed by %s", self.bug_id, interaction.user
        )

    # -- Analyze handler -------------------------------------------------------

    async def _handle_analyze(self, interaction: discord.Interaction) -> None:
        """Trigger AI analysis for the bug and post results in the thread."""
        # a) Defer immediately (ephemeral -- real content goes to the thread)
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client

        # b) Fetch the bug from DB
        bug = await bot.bug_repo.get_bug(self.bug_id)
        if bug is None:
            await interaction.followup.send(
                f"Bug #{self.bug_id} not found.", ephemeral=True
            )
            return

        # c) Concurrent click guard (status-based)
        if bug["status"] == "analyzing":
            await interaction.followup.send(
                "Analysis already in progress.", ephemeral=True
            )
            return
        if bug["status"] in ("triaged", "issue_created", "fix_drafted", "resolved"):
            await interaction.followup.send(
                "This bug has already been analyzed.", ephemeral=True
            )
            return
        if bug["status"] == "dismissed":
            await interaction.followup.send(
                "Cannot analyze a dismissed bug.", ephemeral=True
            )
            return

        # d) Check AI service availability
        if bot.ai_service is None:
            await interaction.followup.send(
                "AI analysis is not configured. Set ANTHROPIC_API_KEY in environment.",
                ephemeral=True,
            )
            return

        # e) Set status to "analyzing"
        await bot.bug_repo.update_status(self.bug_id, "analyzing", str(interaction.user))

        # f) Update the channel embed to show "analyzing" status
        analyzing_bug = await bot.bug_repo.get_bug(self.bug_id)
        analyzing_embed = build_summary_embed(analyzing_bug)
        await interaction.message.edit(
            embed=analyzing_embed, view=build_bug_view(self.bug_id)
        )

        # g) Get the thread
        thread = interaction.message.thread
        if thread is None and bug.get("thread_id"):
            try:
                thread = bot.get_channel(bug["thread_id"])
                if thread is None:
                    thread = await bot.fetch_channel(bug["thread_id"])
            except discord.HTTPException:
                thread = None
        if thread is None:
            # Revert status and inform user
            await bot.bug_repo.update_status(self.bug_id, "received", "system")
            reverted_bug = await bot.bug_repo.get_bug(self.bug_id)
            reverted_embed = build_summary_embed(reverted_bug)
            await interaction.message.edit(
                embed=reverted_embed, view=build_bug_view(self.bug_id)
            )
            await interaction.followup.send(
                "Could not find the bug thread. Please try again.", ephemeral=True
            )
            return

        # h) Post loading message in thread (visible to everyone)
        loading_msg = await thread.send("Analyzing bug report... please wait.")

        # i) Call AI service
        try:
            result = await bot.ai_service.analyze_bug(bug)
        except (anthropic.APIError, ValueError) as exc:
            # On failure: delete loading message, revert status, ephemeral error
            logger.error("AI analysis failed for bug %s: %s", self.bug_id, exc)
            await loading_msg.delete()
            await bot.bug_repo.update_status(self.bug_id, "received", "system")
            # Revert channel embed back to received
            reverted_bug = await bot.bug_repo.get_bug(self.bug_id)
            reverted_embed = build_summary_embed(reverted_bug)
            await interaction.message.edit(
                embed=reverted_embed, view=build_bug_view(self.bug_id)
            )
            await interaction.followup.send(
                "AI analysis failed. Please try again later.", ephemeral=True
            )
            return

        # j) Store analysis results in DB
        updated_bug = await bot.bug_repo.store_analysis(
            self.bug_id, result, str(interaction.user)
        )

        # k) Build and post analysis embed (edit loading message in-place)
        analysis_embed = build_analysis_embed(updated_bug, result)
        await loading_msg.edit(content=None, embed=analysis_embed)

        # l) Store the analysis message ID for reaction tracking
        await bot.bug_repo.store_analysis_message_id(self.bug_id, loading_msg.id)

        # m) Update the channel embed with triaged status + priority badge
        summary_embed = build_summary_embed(updated_bug)
        new_view = build_bug_view(self.bug_id, analyzed=True)
        await interaction.message.edit(embed=summary_embed, view=new_view)

        # n) Confirm to clicker (ephemeral)
        await interaction.followup.send(
            f"Analysis complete for bug #{self.bug_id}. Priority: **{result['priority']}**",
            ephemeral=True,
        )
        logger.info(
            "Bug %s analyzed by %s -- priority %s",
            self.bug_id, interaction.user, result["priority"],
        )

    # -- Create Issue handler --------------------------------------------------

    async def _handle_create_issue(self, interaction: discord.Interaction) -> None:
        """Create a GitHub issue from the bug report and update Discord state."""
        # 1. Defer immediately (GitHub API calls take time)
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client

        # 2. Fetch bug and guard checks
        bug = await bot.bug_repo.get_bug(self.bug_id)
        if bug is None:
            await interaction.followup.send(
                f"Bug #{self.bug_id} not found.", ephemeral=True
            )
            return

        if bug["status"] == "dismissed":
            await interaction.followup.send(
                "Cannot create issue for a dismissed bug.", ephemeral=True
            )
            return

        if bug["status"] not in (
            "triaged", "issue_created", "fix_drafted", "resolved"
        ):
            await interaction.followup.send(
                "Bug must be analyzed first. Click **Analyze** before creating an issue.",
                ephemeral=True,
            )
            return

        if bug.get("github_issue_number") is not None:
            await interaction.followup.send(
                f"Issue already exists: {bug['github_issue_url']}",
                ephemeral=True,
            )
            return

        # 3. Check GitHub service availability
        if bot.github_service is None:
            await interaction.followup.send(
                "GitHub integration is not configured.", ephemeral=True
            )
            return

        # 4. Get guild config
        config = await bot.github_config_repo.get_config(interaction.guild_id)
        if config is None:
            await interaction.followup.send(
                "No GitHub repo connected. Run `/init` first.", ephemeral=True
            )
            return

        owner = config["repo_owner"]
        repo = config["repo_name"]

        try:
            # 5. Build issue title
            display_title = _get_display_title(bug)
            title = f"[Bug #{bug['hash_id']}] {display_title}"

            # 6. Build labels
            label_tuples = []
            priority_label = get_priority_label(bug.get("priority"))
            if priority_label:
                label_tuples.append(priority_label)
            area_label = get_area_label(bug.get("ai_affected_area"))
            if area_label:
                label_tuples.append(area_label)
            label_tuples.append(get_bot_label())

            label_names = [name for name, _ in label_tuples]

            # 7. Ensure labels exist in the repo
            await bot.github_service.ensure_labels(owner, repo, label_tuples)

            # 8. Build issue body
            body = build_issue_body(bug, guild_id=interaction.guild_id)

            # 9. Create the issue
            issue = await bot.github_service.create_issue(
                owner, repo, title, body, label_names
            )

            # 10. Store in DB
            updated_bug = await bot.bug_repo.store_github_issue(
                self.bug_id,
                issue["number"],
                issue["html_url"],
                str(interaction.user),
            )

            # 11. Update channel embed
            if updated_bug:
                new_embed = build_summary_embed(updated_bug)
                new_view = build_bug_view(
                    self.bug_id, analyzed=True, issue_created=True
                )
                await interaction.message.edit(embed=new_embed, view=new_view)

            # 12. Post in thread
            thread = interaction.message.thread
            if thread is None and bug.get("thread_id"):
                try:
                    thread = bot.get_channel(bug["thread_id"])
                    if thread is None:
                        thread = await bot.fetch_channel(bug["thread_id"])
                except discord.HTTPException:
                    thread = None

            if thread is not None:
                try:
                    await thread.send(
                        f"GitHub issue created: [{title}]({issue['html_url']})"
                    )
                except discord.HTTPException:
                    logger.warning(
                        "Could not post issue link in thread for bug %s",
                        self.bug_id,
                    )

            # 13. Ephemeral confirmation
            await interaction.followup.send(
                f"Issue created: {issue['html_url']}", ephemeral=True
            )
            logger.info(
                "Bug %s -> GitHub issue #%s by %s",
                self.bug_id, issue["number"], interaction.user,
            )

        except Exception as exc:
            logger.error(
                "Failed to create GitHub issue for bug %s: %s",
                self.bug_id, exc,
            )
            await interaction.followup.send(
                "Failed to create issue. Please try again.", ephemeral=True
            )


# -------------------------------------------------------------------------
# View builder helper
# -------------------------------------------------------------------------

def build_bug_view(
    bug_id: str,
    *,
    dismissed: bool = False,
    analyzed: bool = False,
    issue_created: bool = False,
) -> discord.ui.View:
    """Build the action-button view for a bug report embed.

    Args:
        bug_id: The 8-char hex hash ID of the bug.
        dismissed: When ``True`` the Dismiss button is disabled (already
            used).
        analyzed: When ``True`` the Analyze button is disabled (already
            analyzed -- one analysis per bug).
        issue_created: When ``True`` the Create Issue button is disabled
            (issue already exists).

    Returns:
        A ``View`` with ``timeout=None`` (required for persistent views).
    """
    view = discord.ui.View(timeout=None)

    # Dismiss -- active when not yet dismissed, disabled once dismissed
    view.add_item(BugActionButton("dismiss", bug_id, disabled=dismissed))

    # Analyze -- disabled if dismissed (cannot analyze dismissed bugs) or
    # already analyzed (one analysis per bug per locked decision);
    # enabled otherwise (ready for analysis)
    analyze_disabled = dismissed or analyzed
    view.add_item(BugActionButton("analyze", bug_id, disabled=analyze_disabled))

    # Create Issue -- enabled when analyzed but no issue yet;
    # disabled when not analyzed, dismissed, or issue already created
    create_issue_disabled = dismissed or not analyzed or issue_created
    view.add_item(
        BugActionButton("create_issue", bug_id, disabled=create_issue_disabled)
    )

    # Draft Fix -- disabled for now (Plan 03)
    view.add_item(BugActionButton("draft_fix", bug_id, disabled=True))

    return view
