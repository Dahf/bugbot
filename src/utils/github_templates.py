"""Markdown template builders for GitHub issue and PR bodies."""

from src.utils.embeds import _parse_json_field, _format_device_info


def build_discord_thread_url(guild_id: int, thread_id: int) -> str:
    """Build a Discord thread URL from guild and thread IDs."""
    return f"https://discord.com/channels/{guild_id}/{thread_id}"


def _format_console_logs_markdown(raw: str | list | None) -> str:
    """Format console logs for GitHub markdown (plain text, no emoji)."""
    if raw is None:
        return "No console logs available"
    parsed = _parse_json_field(raw)
    if isinstance(parsed, list):
        lines = []
        for entry in parsed:
            if isinstance(entry, dict):
                level = entry.get("level", "info").upper()
                msg = entry.get("message") or ""
                lines.append(f"[{level}] {msg}")
            else:
                lines.append(str(entry))
        return "\n".join(lines) if lines else "No console logs available"
    return str(parsed) if parsed else "No console logs available"


def build_issue_body(bug: dict, guild_id: int | None = None) -> str:
    """Build a GitHub issue body with full bug context.

    Produces a well-structured markdown document with all available
    information from the bug report and AI analysis.
    """
    hash_id = bug.get("hash_id", "unknown")
    description = bug.get("description") or "No description provided"
    steps = bug.get("steps_to_reproduce") or "Not provided"
    device = _format_device_info(bug.get("device_info"))
    app_version = bug.get("app_version") or "N/A"
    severity = bug.get("severity") or "N/A"

    sections = [
        f"## Bug Report #{hash_id}",
        "",
        f"**Description:** {description}",
        "",
        f"**Steps to Reproduce:**",
        steps,
        "",
        "### Environment",
        "| Field | Value |",
        "|-------|-------|",
        f"| Device | {device} |",
        f"| App Version | {app_version} |",
        f"| Severity (reported) | {severity} |",
    ]

    # AI Analysis section (only if the bug has been analyzed)
    ai_root_cause = bug.get("ai_root_cause")
    if ai_root_cause:
        ai_area = bug.get("ai_affected_area") or "N/A"
        ai_severity = bug.get("ai_severity") or "N/A"
        ai_fix = bug.get("ai_suggested_fix") or "N/A"
        priority = bug.get("priority") or "N/A"
        priority_reasoning = bug.get("priority_reasoning") or ""

        sections.extend([
            "",
            "### AI Analysis",
            f"- **Root Cause:** {ai_root_cause}",
            f"- **Affected Area:** {ai_area}",
            f"- **AI Severity:** {ai_severity}",
            f"- **Suggested Fix:** {ai_fix}",
            f"- **Priority:** {priority} -- {priority_reasoning}",
        ])

    # Console logs in a collapsible block
    console_logs = _format_console_logs_markdown(bug.get("console_logs"))
    sections.extend([
        "",
        "### Console Logs",
        "<details>",
        "<summary>Click to expand</summary>",
        "",
        "```",
        console_logs,
        "```",
        "",
        "</details>",
    ])

    # Discord thread link
    thread_id = bug.get("thread_id")
    if guild_id and thread_id:
        thread_url = build_discord_thread_url(guild_id, thread_id)
        sections.extend([
            "",
            "---",
            f":link: [Discord Thread]({thread_url})",
        ])

    sections.extend([
        ":robot: Created by PreserveFood BugBot",
    ])

    return "\n".join(sections)


def build_pr_body(
    bug: dict,
    issue_number: int | None = None,
    discord_thread_url: str | None = None,
) -> str:
    """Build a GitHub PR body with bug context and auto-close reference.

    Includes bug summary, AI analysis, Discord link, and ``Closes #N``
    (only when *issue_number* is provided).
    """
    hash_id = bug.get("hash_id", "unknown")
    title = bug.get("title") or "Untitled"
    description = bug.get("description") or "No description provided"

    # Truncate description excerpt to 200 chars
    desc_excerpt = description[:200]
    if len(description) > 200:
        desc_excerpt += "..."

    sections = [
        f"## Bug Fix: #{hash_id}",
        "",
        f"**Title:** {title}",
        f"**Description:** {desc_excerpt}",
    ]

    # AI analysis summary (if available)
    ai_root_cause = bug.get("ai_root_cause")
    if ai_root_cause:
        ai_area = bug.get("ai_affected_area") or "N/A"
        ai_severity = bug.get("ai_severity") or "N/A"
        ai_fix = bug.get("ai_suggested_fix") or "N/A"

        sections.extend([
            "",
            "### AI Analysis",
            f"- **Root Cause:** {ai_root_cause}",
            f"- **Affected Area:** {ai_area}",
            f"- **Severity:** {ai_severity}",
            f"- **Suggested Fix:** {ai_fix}",
        ])

    if discord_thread_url:
        sections.extend([
            "",
            f":link: [Discord Thread]({discord_thread_url})",
        ])

    if issue_number is not None:
        sections.extend([
            "",
            f"Closes #{issue_number}",
        ])

    sections.extend([
        "",
        "---",
        "> **Note:** This PR was scaffolded by PreserveFood BugBot. "
        "Actual code changes may be provided by an external tool "
        "(e.g., GitHub Copilot, BugBot).",
    ])

    return "\n".join(sections)


def get_priority_label(priority: str | None) -> tuple[str, str] | None:
    """Map a priority string to a (label_name, hex_color) tuple.

    Returns None if priority is None or not recognized.
    """
    mapping = {
        "P1": ("P1-critical", "e11d48"),
        "P2": ("P2-high", "f97316"),
        "P3": ("P3-medium", "eab308"),
        "P4": ("P4-low", "22c55e"),
    }
    if priority is None:
        return None
    # Match on the first two characters (e.g., "P1", "P2")
    key = priority.strip().upper()[:2]
    return mapping.get(key)


def get_area_label(area: str | None) -> tuple[str, str] | None:
    """Map an affected area string to a (label_name, hex_color) tuple.

    Returns None if area is falsy.
    """
    if not area:
        return None
    return (f"area:{area.lower().strip()}", "6366f1")


def get_bot_label() -> tuple[str, str]:
    """Return the bot-created label (label_name, hex_color)."""
    return ("bot-created", "8b5cf6")
