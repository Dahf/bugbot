"""GitHub integration cog -- /init command and webhook event handlers."""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.embeds import build_summary_embed
from src.views.bug_buttons import build_bug_view, _derive_bug_flags

logger = logging.getLogger(__name__)


class RepoSelectView(discord.ui.View):
    """Dropdown view for selecting a repository from multiple options."""

    def __init__(self, repos: list[dict], *, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.selected_repo: dict | None = None

        options = [
            discord.SelectOption(
                label=repo["full_name"],
                value=repo["full_name"],
                description=f"{repo['owner']}/{repo['name']}",
            )
            for repo in repos[:25]  # Discord max 25 options
        ]
        select = discord.ui.Select(
            placeholder="Select a repository...",
            options=options,
        )
        select.callback = self._on_select
        self.add_item(select)
        self._repos_by_name = {r["full_name"]: r for r in repos}

    async def _on_select(self, interaction: discord.Interaction) -> None:
        """Handle repo selection from dropdown."""
        full_name = interaction.data["values"][0]
        self.selected_repo = self._repos_by_name.get(full_name)
        await interaction.response.defer()
        self.stop()


class GitHubIntegration(commands.Cog):
    """Handles /init slash command and GitHub webhook event processing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Webhook event handling
    # ------------------------------------------------------------------

    async def handle_github_event(
        self, event_name: str, payload: dict
    ) -> None:
        """Route a GitHub webhook event to the appropriate handler."""
        if event_name == "pull_request":
            await self.handle_pull_request_event(payload)
        elif event_name == "installation":
            logger.info(
                "GitHub installation event: action=%s",
                payload.get("action"),
            )
        else:
            logger.debug("Ignoring GitHub event: %s", event_name)

    async def handle_pull_request_event(self, payload: dict) -> None:
        """Handle pull_request webhook events (merge, close, review_requested)."""
        action = payload.get("action", "")
        pr_data = payload.get("pull_request", {})
        pr_number = pr_data.get("number")
        pr_url = pr_data.get("html_url", "")
        head_branch = pr_data.get("head", {}).get("ref", "")
        merged = pr_data.get("merged", False)
        repo_data = payload.get("repository", {})
        owner = repo_data.get("owner", {}).get("login", "")
        repo = repo_data.get("name", "")

        # Look up the bug by branch name
        bug = await self.bot.bug_repo.get_bug_by_branch_name(head_branch)
        if bug is None:
            logger.debug(
                "PR #%s branch %s has no matching bug -- not from our bot",
                pr_number, head_branch,
            )
            return

        hash_id = bug["hash_id"]

        if action == "closed" and merged:
            # PR merged -> auto-resolve the bug!
            logger.info(
                "PR #%s merged for bug %s -- auto-resolving",
                pr_number, hash_id,
            )
            await self.bot.bug_repo.update_status(
                hash_id, "resolved", "github-webhook"
            )

            # Delete the branch (GH-10 cleanup)
            if self.bot.github_service and owner and repo:
                try:
                    await self.bot.github_service.delete_branch(
                        owner, repo, head_branch
                    )
                except Exception:
                    logger.warning(
                        "Failed to delete branch %s after merge", head_branch
                    )

            # Update Discord embed and post thread notification
            await self._update_discord_embed(bug)
            await self._post_thread_message(
                bug,
                f"PR #{pr_number} has been merged! Bug resolved.",
            )

        elif action == "closed" and not merged:
            # PR closed without merge -- notify but don't change status
            logger.info(
                "PR #%s closed without merging for bug %s", pr_number, hash_id
            )
            await self._post_thread_message(
                bug,
                f"PR #{pr_number} was closed without merging.",
            )

        elif action == "review_requested":
            logger.info(
                "Review requested on PR #%s for bug %s", pr_number, hash_id
            )
            await self._post_thread_message(
                bug,
                f"Review requested on PR #{pr_number}.",
            )

    async def _update_discord_embed(self, bug: dict) -> None:
        """Fetch the Discord message for a bug and update embed + buttons.

        Non-blocking: logs errors instead of raising so the webhook handler
        always returns 200 to GitHub.
        """
        try:
            # Refetch the bug to get the latest state after status update
            updated_bug = await self.bot.bug_repo.get_bug(bug["hash_id"])
            if updated_bug is None:
                return

            channel_id = updated_bug.get("channel_id")
            message_id = updated_bug.get("message_id")
            if not channel_id or not message_id:
                logger.debug(
                    "Bug %s has no channel/message refs -- skipping embed update",
                    bug["hash_id"],
                )
                return

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException:
                    logger.warning(
                        "Could not fetch channel %s for bug %s",
                        channel_id, bug["hash_id"],
                    )
                    return

            try:
                message = await channel.fetch_message(message_id)
            except discord.HTTPException:
                logger.warning(
                    "Could not fetch message %s for bug %s",
                    message_id, bug["hash_id"],
                )
                return

            new_embed = build_summary_embed(updated_bug)
            flags = _derive_bug_flags(updated_bug)
            new_view = build_bug_view(updated_bug["hash_id"], **flags)
            await message.edit(embed=new_embed, view=new_view)

        except Exception:
            logger.exception(
                "Failed to update Discord embed for bug %s", bug["hash_id"]
            )

    async def _post_thread_message(
        self, bug: dict, content: str
    ) -> None:
        """Post a message in the bug's Discord thread.

        Non-blocking: logs errors instead of raising.
        """
        try:
            thread_id = bug.get("thread_id")
            if not thread_id:
                return

            thread = self.bot.get_channel(thread_id)
            if thread is None:
                try:
                    thread = await self.bot.fetch_channel(thread_id)
                except discord.HTTPException:
                    logger.warning(
                        "Could not fetch thread %s for bug %s",
                        thread_id, bug["hash_id"],
                    )
                    return

            await thread.send(content)
        except Exception:
            logger.exception(
                "Failed to post thread message for bug %s", bug["hash_id"]
            )

    # ------------------------------------------------------------------
    # /init slash command
    # ------------------------------------------------------------------

    @app_commands.command(
        name="init",
        description="Connect a GitHub repository to this server for bug tracking",
    )
    async def init_command(self, interaction: discord.Interaction) -> None:
        """Walk the user through GitHub App installation and repo selection."""
        # 1. Check if GitHub service is configured
        if self.bot.github_service is None:
            await interaction.response.send_message(
                "GitHub integration is not configured. "
                "The bot admin needs to set GitHub App environment variables.",
                ephemeral=True,
            )
            return

        # 2. Check if guild already has a config
        existing = await self.bot.github_config_repo.get_config(
            interaction.guild_id
        )
        if existing:
            logger.info(
                "Guild %s re-running /init (current repo: %s/%s)",
                interaction.guild_id,
                existing["repo_owner"],
                existing["repo_name"],
            )

        # 3. Defer -- the polling loop takes time
        await interaction.response.defer(ephemeral=True)

        # 4. Send the install link
        app_name = self.bot.config.GITHUB_APP_NAME or "your-github-app"
        install_url = (
            f"https://github.com/apps/{app_name}/installations/new"
        )

        reconfigure_note = ""
        if existing:
            reconfigure_note = (
                f"\n\nCurrently connected to **{existing['repo_owner']}"
                f"/{existing['repo_name']}**. "
                "Completing this flow will update the configuration."
            )

        await interaction.followup.send(
            f"**Step 1:** Install the GitHub App on your repository.\n"
            f"{install_url}\n\n"
            f"I'll wait up to 5 minutes for the installation to be detected..."
            f"{reconfigure_note}",
            ephemeral=True,
        )

        # 5. Get known installations before polling (to detect new ones)
        try:
            known_installations = await self.bot.github_service.list_installations()
            known_ids = {inst.id for inst in known_installations}
        except Exception as exc:
            logger.error("Failed to list existing installations: %s", exc)
            await interaction.followup.send(
                "Failed to connect to GitHub API. Please try again later.",
                ephemeral=True,
            )
            return

        # 6. Polling loop: every 5 seconds for up to 5 minutes
        new_installation = None
        for _ in range(60):
            await asyncio.sleep(5)
            try:
                current = await self.bot.github_service.list_installations()
                for inst in current:
                    if inst.id not in known_ids:
                        new_installation = inst
                        break
                if new_installation:
                    break
            except Exception as exc:
                logger.warning("Polling error: %s", exc)
                continue

        if new_installation is None:
            await interaction.followup.send(
                "Installation not detected within 5 minutes. "
                "Run `/init` again after installing the GitHub App.",
                ephemeral=True,
            )
            return

        # 7. List repos for the new installation
        try:
            repos = await self.bot.github_service.list_installation_repos(
                new_installation.id
            )
        except Exception as exc:
            logger.error("Failed to list installation repos: %s", exc)
            await interaction.followup.send(
                "Detected installation but failed to list repositories. "
                "Please try again.",
                ephemeral=True,
            )
            return

        if not repos:
            await interaction.followup.send(
                "The GitHub App was installed but has no repository access. "
                "Please update the App's repository permissions and run `/init` again.",
                ephemeral=True,
            )
            return

        # 8. Select repo (auto-select if only one)
        if len(repos) == 1:
            selected = repos[0]
        else:
            select_view = RepoSelectView(repos)
            await interaction.followup.send(
                "**Step 2:** Multiple repositories detected. "
                "Select the repository to connect:",
                view=select_view,
                ephemeral=True,
            )
            timed_out = await select_view.wait()
            if timed_out or select_view.selected_repo is None:
                await interaction.followup.send(
                    "Repository selection timed out. Run `/init` again.",
                    ephemeral=True,
                )
                return
            selected = select_view.selected_repo

        # 9. Store config
        await self.bot.github_config_repo.set_config(
            guild_id=interaction.guild_id,
            installation_id=new_installation.id,
            repo_owner=selected["owner"],
            repo_name=selected["name"],
        )

        # 10. Confirmation embed
        embed = discord.Embed(
            title="GitHub Connected",
            description=(
                f"Repository: **{selected['owner']}/{selected['name']}**\n\n"
                "You can now use the **Create Issue** button on analyzed bugs "
                "to create GitHub issues directly from Discord."
            ),
            color=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        logger.info(
            "Guild %s connected to GitHub repo %s/%s (installation %s)",
            interaction.guild_id,
            selected["owner"],
            selected["name"],
            new_installation.id,
        )


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(GitHubIntegration(bot))
