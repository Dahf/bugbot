"""Persistent DynamicItem buttons for bug report actions."""

import logging
import re

import discord

from src.utils.embeds import build_summary_embed

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
        elif self.action in ("analyze", "create_issue", "draft_fix"):
            # These are disabled in Phase 1, but handle gracefully just in case
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


# -------------------------------------------------------------------------
# View builder helper
# -------------------------------------------------------------------------

def build_bug_view(
    bug_id: str, *, dismissed: bool = False
) -> discord.ui.View:
    """Build the action-button view for a bug report embed.

    Args:
        bug_id: The 8-char hex hash ID of the bug.
        dismissed: When ``True`` the Dismiss button is disabled (already
            used).  Analyze, Create Issue, and Draft Fix are always disabled
            in Phase 1 regardless of this flag.

    Returns:
        A ``View`` with ``timeout=None`` (required for persistent views).
    """
    view = discord.ui.View(timeout=None)

    # Dismiss -- active when not yet dismissed, disabled once dismissed
    view.add_item(BugActionButton("dismiss", bug_id, disabled=dismissed))

    # Phase 2-3 buttons -- always disabled for now
    view.add_item(BugActionButton("analyze", bug_id, disabled=True))
    view.add_item(BugActionButton("create_issue", bug_id, disabled=True))
    view.add_item(BugActionButton("draft_fix", bug_id, disabled=True))

    return view
