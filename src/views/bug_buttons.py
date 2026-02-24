"""Persistent DynamicItem buttons for bug report actions."""

import logging
import re

import anthropic
import discord

from src.services.copilot_fix_service import CopilotFixService
from src.utils.embeds import build_summary_embed, build_analysis_embed, _get_display_title
from src.utils.github_templates import (
    build_issue_body,
    build_pr_body,
    build_code_fix_pr_body,
    build_context_commit_content,
    build_discord_thread_url,
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
            await self._handle_draft_fix(interaction)
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
                flags = _derive_bug_flags(updated_bug)
                new_embed = build_summary_embed(updated_bug)
                new_view = build_bug_view(self.bug_id, **flags)
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
            resp_data = getattr(getattr(exc, 'response', None), 'parsed_data', None)
            logger.error(
                "Failed to create GitHub issue for bug %s: %s | detail: %s",
                self.bug_id, exc, resp_data,
            )
            await interaction.followup.send(
                "Failed to create issue. Please try again.", ephemeral=True
            )

    # -- Draft Fix handler -----------------------------------------------------

    async def _handle_draft_fix(self, interaction: discord.Interaction) -> None:
        """Create a feature branch, run agentic AI code fix, and open a PR."""
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
                "Cannot draft a fix for a dismissed bug.", ephemeral=True
            )
            return

        if bug["status"] not in (
            "triaged", "issue_created", "fix_drafted", "resolved"
        ):
            await interaction.followup.send(
                "Bug must be analyzed first. Click **Analyze** before drafting a fix.",
                ephemeral=True,
            )
            return

        # Block re-trigger if branch already exists
        if bug.get("github_branch_name") is not None:
            pr_url = bug.get("github_pr_url", "")
            branch = bug["github_branch_name"]
            msg = f"A fix branch already exists: `{branch}`."
            if pr_url:
                msg += f" PR: {pr_url}"
            await interaction.followup.send(msg, ephemeral=True)
            return

        # 3. Check GitHub service availability
        if bot.github_service is None:
            await interaction.followup.send(
                "GitHub integration is not configured.", ephemeral=True
            )
            return

        # 3b. Check code fix service availability
        if bot.code_fix_service is None:
            await interaction.followup.send(
                "AI code fix is not configured. Check CODE_FIX_MODE and required credentials.",
                ephemeral=True,
            )
            return

        is_copilot = isinstance(bot.code_fix_service, CopilotFixService)

        # 4. Get guild config
        config = await bot.github_config_repo.get_config(interaction.guild_id)
        if config is None:
            await interaction.followup.send(
                "No GitHub repo connected. Run `/init` first.", ephemeral=True
            )
            return

        owner = config["repo_owner"]
        repo = config["repo_name"]
        branch_name = None

        try:
            display_title = _get_display_title(bug)

            if is_copilot:
                # Copilot mode: skip branch creation (Copilot creates its own)
                branch_name = None
                default_branch, _ = (
                    await bot.github_service.get_default_branch_sha(owner, repo)
                )
            else:
                # 5. Build branch name
                branch_name = bot.github_service.build_branch_name(
                    bug["hash_id"], display_title
                )

                # 6. Get default branch SHA
                default_branch, base_sha = (
                    await bot.github_service.get_default_branch_sha(owner, repo)
                )

                # 7. Create branch (GH-08: always a feature branch, never default)
                try:
                    await bot.github_service.create_branch(
                        owner, repo, branch_name, base_sha
                    )
                except Exception as branch_exc:
                    # 422 = ref already exists
                    if "422" in str(branch_exc) or "Reference already exists" in str(branch_exc):
                        await interaction.followup.send(
                            f"Branch `{branch_name}` already exists. "
                            "This bug may already have a draft fix.",
                            ephemeral=True,
                        )
                        return
                    raise

            # 7a. Identify relevant source files (non-fatal)
            relevant_paths: list[str] = []
            try:
                relevant_paths = await bot.github_service.identify_relevant_files(
                    owner, repo, bug.get("ai_affected_area", ""), ref=default_branch
                )
            except Exception as exc:
                logger.warning(
                    "Failed to identify relevant files for bug %s: %s",
                    self.bug_id, exc,
                )

            # 8. Get thread early (needed for progress messages)
            thread = interaction.message.thread
            if thread is None and bug.get("thread_id"):
                try:
                    thread = bot.get_channel(bug["thread_id"])
                    if thread is None:
                        thread = await bot.fetch_channel(bug["thread_id"])
                except discord.HTTPException:
                    thread = None

            # 9. Define progress callback for live Discord updates
            async def post_progress(message: str):
                if thread is not None:
                    try:
                        await thread.send(f"\U0001f527 {message}")
                    except discord.HTTPException:
                        pass
                logger.info("Code fix progress [%s]: %s", self.bug_id, message)

            # 10. Run code fix service (anthropic or copilot)
            await post_progress(
                "Starting Copilot code fix..." if is_copilot
                else "Starting AI code fix generation..."
            )
            fix_result = await bot.code_fix_service.generate_fix(
                github_service=bot.github_service,
                owner=owner,
                repo=repo,
                branch=branch_name or "",
                bug=bug,
                relevant_paths=relevant_paths,
                progress_callback=post_progress,
            )

            # 11. Handle failure
            if not fix_result.get("success"):
                error_msg = fix_result.get("error", "Unknown error")
                logger.error(
                    "Code fix generation failed for bug %s: %s",
                    self.bug_id, error_msg,
                )
                if thread is not None:
                    try:
                        await thread.send(
                            f"\u274c Code fix generation failed: {error_msg}"
                        )
                    except discord.HTTPException:
                        pass
                # If nothing was committed, skip PR creation
                if not fix_result.get("changed_files"):
                    await interaction.followup.send(
                        f"Code fix generation failed: {error_msg}",
                        ephemeral=True,
                    )
                    return

            # 12-14. PR creation (mode-dependent)
            if is_copilot and fix_result.get("copilot_pr"):
                # Copilot already created the PR
                pr = fix_result["copilot_pr"]
                pr_title = pr.get("title", f"fix: {display_title}")
                branch_name = pr.get("branch", "copilot/unknown")
            else:
                # Anthropic mode: build PR body and create it ourselves
                issue_number = bug.get("github_issue_number")
                discord_thread_url = None
                if bug.get("thread_id") and interaction.guild_id:
                    discord_thread_url = build_discord_thread_url(
                        interaction.guild_id, bug["thread_id"]
                    )
                pr_body = build_code_fix_pr_body(
                    bug,
                    issue_number=issue_number,
                    discord_thread_url=discord_thread_url,
                    process_log=fix_result.get("process_log", {}),
                    changed_files=fix_result.get("changed_files", {}),
                    validation_passed=fix_result.get("validation_passed", False),
                )
                pr_title = f"fix: {display_title} (#{bug['hash_id']})"
                pr = await bot.github_service.create_pull_request(
                    owner, repo, pr_title, pr_body, branch_name, default_branch
                )

            # 15. Store in DB
            updated_bug = await bot.bug_repo.store_github_pr(
                self.bug_id,
                pr["number"],
                pr["html_url"],
                branch_name,
                str(interaction.user),
            )

            # 16. Update channel embed
            if updated_bug:
                flags = _derive_bug_flags(updated_bug)
                new_embed = build_summary_embed(updated_bug)
                new_view = build_bug_view(self.bug_id, **flags)
                await interaction.message.edit(embed=new_embed, view=new_view)

            # 17. Post PR link in thread
            if thread is not None:
                try:
                    await thread.send(
                        f"Draft fix PR created: [{pr_title}]({pr['html_url']})"
                    )
                except discord.HTTPException:
                    logger.warning(
                        "Could not post PR link in thread for bug %s",
                        self.bug_id,
                    )

            # 18. Post completion embed in thread
            if thread is not None:
                try:
                    if is_copilot:
                        completion_embed = discord.Embed(
                            title="Copilot Code Fix Complete",
                            color=0x22c55e,
                        )
                        completion_embed.add_field(
                            name="Mode",
                            value="GitHub Copilot Agent",
                            inline=True,
                        )
                        completion_embed.add_field(
                            name="Pull Request",
                            value=f"[{pr_title}]({pr['html_url']})",
                            inline=False,
                        )
                        completion_embed.set_footer(
                            text="Fix generated by GitHub Copilot coding agent"
                        )
                    else:
                        process_log = fix_result.get("process_log", {})
                        total_tokens = process_log.get("total_tokens", {})
                        changed_files = fix_result.get("changed_files", {})
                        validation_ok = fix_result.get("validation_passed", False)
                        rounds_taken = fix_result.get("rounds_taken", 0)

                        embed_color = 0x22c55e if validation_ok else 0xeab308
                        completion_embed = discord.Embed(
                            title="AI Code Fix Complete",
                            color=embed_color,
                        )
                        if changed_files:
                            files_list = "\n".join(
                                f"`{p}`" for p in changed_files.keys()
                            )
                            completion_embed.add_field(
                                name="Files Changed",
                                value=files_list,
                                inline=True,
                            )
                        completion_embed.add_field(
                            name="Rounds Taken",
                            value=str(rounds_taken),
                            inline=True,
                        )
                        validation_text = (
                            "\u2705 Passed" if validation_ok else "\u26a0\ufe0f Partial"
                        )
                        completion_embed.add_field(
                            name="Validation",
                            value=validation_text,
                            inline=True,
                        )
                        completion_embed.add_field(
                            name="Pull Request",
                            value=f"[{pr_title}]({pr['html_url']})",
                            inline=False,
                        )
                        if not validation_ok:
                            rounds_log = process_log.get("rounds", [])
                            failed_gates = []
                            for rnd in rounds_log:
                                lint = rnd.get("lint", {})
                                if lint and not lint.get("passed", True):
                                    failed_gates.append(
                                        f"Lint ({lint.get('linter', 'unknown')})"
                                    )
                                sr = rnd.get("self_review", {})
                                if sr and not sr.get("passed", True):
                                    failed_gates.append("Self-review")
                                ci = rnd.get("ci", {})
                                if ci and ci.get("status") == "failed":
                                    failed_gates.append("CI")
                            if failed_gates:
                                unique_gates = list(dict.fromkeys(failed_gates))
                                completion_embed.add_field(
                                    name="Failed Gates",
                                    value=", ".join(unique_gates),
                                    inline=False,
                                )
                        input_tok = total_tokens.get("input", 0)
                        output_tok = total_tokens.get("output", 0)
                        completion_embed.set_footer(
                            text=(
                                f"Tokens: {input_tok:,} input + "
                                f"{output_tok:,} output = "
                                f"{input_tok + output_tok:,} total"
                            )
                        )
                    await thread.send(embed=completion_embed)
                except discord.HTTPException:
                    logger.warning(
                        "Could not post completion embed in thread for bug %s",
                        self.bug_id,
                    )

            # 19. Ephemeral confirmation
            validation_status = (
                "all gates passed"
                if fix_result.get("validation_passed")
                else "review recommended"
            )
            await interaction.followup.send(
                f"AI code fix PR created ({validation_status}): {pr['html_url']}",
                ephemeral=True,
            )
            logger.info(
                "Bug %s -> AI fix PR #%s by %s (rounds: %d, validation: %s)",
                self.bug_id, pr["number"], interaction.user,
                fix_result.get("rounds_taken", 0),
                fix_result.get("validation_passed", False),
            )

        except Exception as exc:
            logger.error(
                "Failed to create draft fix for bug %s: %s",
                self.bug_id, exc,
            )
            # Cleanup: only delete branches we created (not Copilot's)
            if branch_name is not None and not is_copilot:
                try:
                    await bot.github_service.delete_branch(
                        owner, repo, branch_name
                    )
                except Exception:
                    logger.warning(
                        "Failed to cleanup branch %s after draft fix error",
                        branch_name,
                    )
            await interaction.followup.send(
                "Failed to create draft fix. Please try again.", ephemeral=True
            )


# -------------------------------------------------------------------------
# Bug flag derivation helper
# -------------------------------------------------------------------------


def _derive_bug_flags(bug: dict) -> dict:
    """Derive ``build_bug_view`` keyword arguments from a bug dict.

    Centralises the status-to-flag mapping so that every caller of
    ``build_bug_view`` produces consistent button states.
    """
    status = bug.get("status", "received")
    return {
        "dismissed": status == "dismissed",
        "analyzed": status in (
            "triaged", "issue_created", "fix_drafted", "resolved"
        ),
        "issue_created": bug.get("github_issue_number") is not None,
        "fix_drafted": bug.get("github_branch_name") is not None,
    }


# -------------------------------------------------------------------------
# View builder helper
# -------------------------------------------------------------------------

def build_bug_view(
    bug_id: str,
    *,
    dismissed: bool = False,
    analyzed: bool = False,
    issue_created: bool = False,
    fix_drafted: bool = False,
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
        fix_drafted: When ``True`` the Draft Fix button is disabled
            (branch/PR already exists).

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

    # Draft Fix -- enabled when analyzed and no fix drafted yet;
    # disabled when not analyzed, dismissed, or fix already drafted
    draft_fix_disabled = dismissed or not analyzed or fix_drafted
    view.add_item(
        BugActionButton("draft_fix", bug_id, disabled=draft_fix_disabled)
    )

    return view
