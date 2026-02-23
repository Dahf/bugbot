"""Embed builder helpers for summary and thread detail views."""

from datetime import datetime

import discord

# -----------------------------------------------------------------------
# Status colour and emoji mappings
# -----------------------------------------------------------------------

STATUS_COLORS: dict[str, discord.Colour] = {
    "received": discord.Colour(0xED4245),       # Red
    "analyzing": discord.Colour(0x3498DB),       # Blue
    "triaged": discord.Colour(0xE67E22),         # Orange
    "issue_created": discord.Colour(0x9B59B6),   # Purple
    "fix_drafted": discord.Colour(0xF1C40F),     # Gold
    "resolved": discord.Colour(0x2ECC71),        # Green
    "dismissed": discord.Colour(0x95A5A6),       # Grey
}

STATUS_EMOJI: dict[str, str] = {
    "received": "\U0001f534",       # Red circle
    "analyzing": "\U0001f535",      # Blue circle
    "triaged": "\U0001f7e0",        # Orange circle
    "issue_created": "\U0001f7e3",  # Purple circle
    "fix_drafted": "\U0001f7e1",    # Yellow circle
    "resolved": "\U0001f7e2",       # Green circle
    "dismissed": "\u26aa",          # White circle
}

# -----------------------------------------------------------------------
# Summary embed (main channel)
# -----------------------------------------------------------------------


def build_summary_embed(bug: dict) -> discord.Embed:
    """Build the summary embed posted to the main bug-reports channel.

    Per CONTEXT.md decisions the summary embed shows **only** title, user,
    status, and severity.  Full details go in the per-bug thread.

    For dismissed bugs the embed uses grey colour and a ``[DISMISSED]``
    title prefix.
    """
    status = bug.get("status", "received")
    hash_id = bug["hash_id"]
    title = bug.get("title") or "Untitled Bug Report"

    # Dismissed styling
    if status == "dismissed":
        embed_title = f"[DISMISSED] #{hash_id} \u2014 {title}"
        description = "_This bug report has been dismissed._"
    else:
        embed_title = f"#{hash_id} \u2014 {title}"
        description = None

    # Parse timestamp
    created_at_str = bug.get("created_at")
    try:
        timestamp = datetime.fromisoformat(created_at_str) if created_at_str else None
    except (TypeError, ValueError):
        timestamp = None

    embed = discord.Embed(
        title=embed_title[:256],  # Discord title limit
        description=description,
        color=STATUS_COLORS.get(status, discord.Colour.default()),
        timestamp=timestamp,
    )

    status_display = f"{STATUS_EMOJI.get(status, '')} {status.replace('_', ' ').title()}"
    embed.add_field(name="Status", value=status_display, inline=True)
    embed.add_field(
        name="Severity",
        value=bug.get("severity") or "Unknown",
        inline=True,
    )
    embed.add_field(
        name="Reporter",
        value=bug.get("user_id") or "Unknown",
        inline=True,
    )
    embed.set_footer(text=f"Bug #{hash_id}")

    return embed


# -----------------------------------------------------------------------
# Thread detail message
# -----------------------------------------------------------------------

_MAX_CONSOLE_LOG_LEN = 1500
_MAX_MESSAGE_LEN = 1900  # buffer under Discord's 2000-char limit


def build_thread_detail_message(bug: dict) -> str:
    """Build the full-detail text message for the per-bug thread.

    Includes all available fields with ``N/A`` fallbacks for missing data.
    Console logs are wrapped in a code block and truncated at 1 500 chars.
    """
    hash_id = bug.get("hash_id", "????")

    sections: list[str] = [
        f"## Bug Report #{hash_id}",
        f"**Title:** {bug.get('title') or 'N/A'}",
        f"**Description:** {bug.get('description') or 'N/A'}",
        f"**Reporter:** {bug.get('user_id') or 'N/A'}",
        f"**Device:** {bug.get('device_info') or 'N/A'}",
        f"**App Version:** {bug.get('app_version') or 'N/A'}",
        f"**Timestamp:** {bug.get('created_at') or 'N/A'}",
    ]

    # Steps to reproduce
    steps = bug.get("steps_to_reproduce") or "N/A"
    sections.append(f"**Steps to Reproduce:** {steps}")

    # Console logs -- may be very long; truncate and wrap in code block
    console_logs = bug.get("console_logs") or "N/A"
    if console_logs != "N/A" and len(console_logs) > _MAX_CONSOLE_LOG_LEN:
        console_logs = console_logs[:_MAX_CONSOLE_LOG_LEN] + "\n... (truncated)"
    sections.append(f"**Console Logs:**\n```\n{console_logs}\n```")

    message = "\n\n".join(sections)

    # Final safety truncation to stay under 2000-char Discord message limit
    if len(message) > _MAX_MESSAGE_LEN:
        # Truncate the description to make room
        truncation_note = "\n\n_... message truncated to fit Discord limits_"
        message = message[: _MAX_MESSAGE_LEN - len(truncation_note)] + truncation_note

    return message


# -----------------------------------------------------------------------
# Thread helpers
# -----------------------------------------------------------------------


def get_thread_name(hash_id: str, title: str | None) -> str:
    """Return a thread name in the format ``#<hash_id> -- <title>``.

    Truncates to 100 characters (Discord thread name limit).
    """
    display_title = title or "Untitled Bug Report"
    name = f"#{hash_id} \u2014 {display_title}"
    return name[:100]


def get_auto_archive_duration(guild: discord.Guild) -> int:
    """Return the longest auto-archive duration available for *guild*.

    Duration depends on the server's Nitro boost level:
    - Tier >= 2  -> 10 080 min (7 days)
    - Tier >= 1  -> 4 320 min (3 days)
    - Free       -> 1 440 min (1 day)
    """
    if guild.premium_tier >= 2:
        return 10080
    if guild.premium_tier >= 1:
        return 4320
    return 1440
