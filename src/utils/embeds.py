"""Embed builder helpers for summary and thread detail views."""

import json
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

SEVERITY_COLORS: dict[str, discord.Colour] = {
    "critical": discord.Colour(0xED4245),  # Red
    "high": discord.Colour(0xE67E22),       # Orange
    "medium": discord.Colour(0xF1C40F),     # Yellow
    "low": discord.Colour(0x2ECC71),        # Green
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


def _parse_json_field(value: str | list | dict | None) -> str | list | dict | None:
    """Parse a JSON string back into a Python object, or return as-is."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _format_device_info(raw: str | dict | None) -> str:
    """Format device_info for display, handling both object and string forms."""
    if raw is None:
        return "N/A"
    parsed = _parse_json_field(raw)
    if isinstance(parsed, dict):
        platform = parsed.get("platform", "?")
        os_version = parsed.get("osVersion", "?")
        return f"{platform} {os_version}"
    return str(parsed) or "N/A"


def _format_console_logs(raw: str | list | None) -> str:
    """Format console_logs for display, handling both array and string forms.

    Returns the full formatted log string without truncation.  Callers are
    responsible for splitting into Discord-safe chunks.
    """
    if raw is None:
        return "N/A"
    parsed = _parse_json_field(raw)
    if isinstance(parsed, list):
        lines = []
        for entry in parsed:
            if isinstance(entry, dict):
                level = entry.get("level", "info")
                icon = "\U0001f534" if level == "error" else "\U0001f7e1" if level == "warn" else "\u26aa"
                msg = entry.get("message") or ""
                lines.append(f"{icon} {msg}")
            else:
                lines.append(str(entry))
        return "\n".join(lines)
    return str(parsed)


def build_console_log_messages(bug: dict) -> list[str]:
    """Build one or more Discord messages containing all console logs.

    Splits into multiple messages of up to 1900 chars each so that
    no logs are truncated.  Returns an empty list if there are no logs.
    """
    logs_text = _format_console_logs(bug.get("console_logs"))
    if logs_text == "N/A":
        return []

    max_chunk = 1900 - len("**Console Logs:**\n```\n\n```")  # ~1870
    chunks: list[str] = []
    lines = logs_text.split("\n")
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_chunk and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    messages: list[str] = []
    for i, chunk in enumerate(chunks):
        header = "**Console Logs:**" if i == 0 else f"**Console Logs (continued {i + 1}/{len(chunks)}):**"
        messages.append(f"{header}\n```\n{chunk}\n```")

    return messages


def _get_display_title(bug: dict) -> str:
    """Get a display title from title or description."""
    title = bug.get("title")
    if title:
        return title
    description = bug.get("description") or ""
    if description:
        # Use first line or first 80 chars of description as title
        first_line = description.split("\n")[0]
        if len(first_line) > 80:
            return first_line[:77] + "..."
        return first_line
    return "Untitled Bug Report"


def _get_reporter_display(bug: dict) -> str:
    """Get reporter display string, preferring name over raw user_id."""
    name = bug.get("reporter_name")
    user_id = bug.get("user_id") or "Unknown"
    if name:
        return f"{name} ({user_id[:8]}...)" if len(user_id) > 8 else f"{name} ({user_id})"
    return user_id


def build_summary_embed(bug: dict) -> discord.Embed:
    """Build the summary embed posted to the main bug-reports channel.

    Shows title/description, user, status, and device info.
    Full details go in the per-bug thread.

    For dismissed bugs the embed uses grey colour and a ``[DISMISSED]``
    title prefix.
    """
    status = bug.get("status", "received")
    hash_id = bug["hash_id"]
    title = _get_display_title(bug)

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
        value=(bug.get("severity") or "N/A").title(),
        inline=True,
    )
    embed.add_field(
        name="Reporter",
        value=_get_reporter_display(bug),
        inline=True,
    )
    embed.add_field(
        name="Device",
        value=_format_device_info(bug.get("device_info")),
        inline=True,
    )

    # Priority badge -- only shown when the bug has been analyzed
    priority = bug.get("priority")
    if priority:
        embed.add_field(
            name="Priority",
            value=f"**{priority}**",
            inline=True,
        )

    embed.set_footer(text=f"Bug #{hash_id}")

    # Screenshot as embed image (signed URL from Supabase)
    screenshot_url = bug.get("screenshot_url")
    if screenshot_url:
        embed.set_image(url=screenshot_url)

    return embed


# -----------------------------------------------------------------------
# Analysis embed (bug thread)
# -----------------------------------------------------------------------


def build_analysis_embed(bug: dict, analysis: dict) -> discord.Embed:
    """Build the AI analysis results embed posted in the bug's thread.

    Colour-coded by AI-assessed severity.  Includes root cause, affected
    area, severity, priority with reasoning, suggested fix, and a token
    usage footer.
    """
    severity = analysis["severity"]
    total_tokens = analysis["usage"]["total_tokens"]

    embed = discord.Embed(
        title=f"AI Analysis -- #{bug['hash_id']}",
        color=SEVERITY_COLORS.get(severity, discord.Colour.default()),
    )
    embed.add_field(name="Root Cause", value=analysis["root_cause"], inline=False)
    embed.add_field(name="Affected Area", value=analysis["affected_area"], inline=True)
    embed.add_field(name="Severity", value=severity.title(), inline=True)
    embed.add_field(
        name="Priority",
        value=f"**{analysis['priority']}** -- {analysis['priority_reasoning']}",
        inline=False,
    )
    embed.add_field(name="Suggested Fix", value=analysis["suggested_fix"], inline=False)

    # Token usage footer
    if total_tokens >= 1000:
        token_display = f"~{total_tokens / 1000:.1f}k tokens"
    else:
        token_display = f"~{total_tokens} tokens"
    embed.set_footer(text=f"Analysis by Claude | {token_display}")

    return embed


# -----------------------------------------------------------------------
# Thread detail message
# -----------------------------------------------------------------------

_MAX_MESSAGE_LEN = 1900  # buffer under Discord's 2000-char limit


def build_thread_detail_message(bug: dict) -> str:
    """Build the full-detail text message for the per-bug thread.

    Includes all available fields with ``N/A`` fallbacks for missing data.
    Handles Supabase payload structure (device_info as object, console_logs
    as array of {level, message} entries).
    """
    hash_id = bug.get("hash_id", "????")
    display_title = _get_display_title(bug)

    sections: list[str] = [
        f"## Bug Report #{hash_id}",
        f"**Description:** {bug.get('description') or 'N/A'}",
        f"**Reporter:** {_get_reporter_display(bug)}",
        f"**Device:** {_format_device_info(bug.get('device_info'))}",
        f"**App Version:** {bug.get('app_version') or 'N/A'}",
        f"**Timestamp:** {bug.get('created_at') or 'N/A'}",
    ]

    # Steps to reproduce (optional — not present in all Supabase payloads)
    steps = bug.get("steps_to_reproduce")
    if steps:
        sections.append(f"**Steps to Reproduce:** {steps}")

    # Console logs are sent as separate message(s) via build_console_log_messages()

    message = "\n\n".join(sections)

    # Final safety truncation to stay under 2000-char Discord message limit
    if len(message) > _MAX_MESSAGE_LEN:
        truncation_note = "\n\n_... message truncated to fit Discord limits_"
        message = message[: _MAX_MESSAGE_LEN - len(truncation_note)] + truncation_note

    return message


# -----------------------------------------------------------------------
# Thread helpers
# -----------------------------------------------------------------------


def get_thread_name(hash_id: str, bug: dict) -> str:
    """Return a thread name in the format ``#<hash_id> -- <title>``.

    Uses title or description excerpt as display name.
    Truncates to 100 characters (Discord thread name limit).
    """
    display_title = _get_display_title(bug)
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
