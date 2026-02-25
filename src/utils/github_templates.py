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


def build_context_commit_content(bug: dict, source_files: list[dict]) -> str:
    """Build the markdown content for the ``.bugbot/context.md`` commit.

    This file is committed to the feature branch to give external tools
    (Copilot, BugBot) and reviewers full context about the bug and
    the relevant source code.

    Each source file snippet is limited to the first 200 lines to keep
    the commit size manageable.
    """
    hash_id = bug.get("hash_id", "unknown")
    title = bug.get("title") or "Untitled"
    description = bug.get("description") or "No description provided"
    severity = bug.get("severity") or "N/A"
    ai_root_cause = bug.get("ai_root_cause") or "N/A"
    ai_area = bug.get("ai_affected_area") or "N/A"
    ai_fix = bug.get("ai_suggested_fix") or "N/A"

    sections = [
        f"# Bug Context: #{hash_id}",
        "",
        "## Bug Report",
        f"**Title:** {title}",
        f"**Description:** {description}",
        f"**Severity:** {severity}",
        "",
        "## AI Analysis",
        f"- **Root Cause:** {ai_root_cause}",
        f"- **Affected Area:** {ai_area}",
        f"- **Suggested Fix:** {ai_fix}",
        "",
        "## Relevant Source Files",
    ]

    if not source_files:
        sections.append("")
        sections.append("No relevant source files identified from repository.")
    else:
        for sf in source_files:
            path = sf["path"]
            content = sf["content"]
            # Determine file extension for syntax highlighting
            dot_idx = path.rfind(".")
            ext = path[dot_idx + 1:] if dot_idx != -1 else ""
            # Limit to first 200 lines
            lines = content.splitlines()
            if len(lines) > 200:
                snippet = "\n".join(lines[:200])
                truncation_note = f"\n\n_(truncated -- showing first 200 of {len(lines)} lines)_"
            else:
                snippet = content
                truncation_note = ""

            sections.extend([
                "",
                f"### {path}",
                f"```{ext}",
                snippet,
                "```",
            ])
            if truncation_note:
                sections.append(truncation_note)

    return "\n".join(sections)


def build_pr_body(
    bug: dict,
    issue_number: int | None = None,
    discord_thread_url: str | None = None,
    source_files: list[dict] | None = None,
) -> str:
    """Build a GitHub PR body with bug context and auto-close reference.

    Includes bug summary, AI analysis, Discord link, optional source file
    references, and ``Closes #N`` (only when *issue_number* is provided).
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

    # Relevant source files section (if identified)
    if source_files:
        sections.extend([
            "",
            "### Relevant Source Files",
        ])
        for sf in source_files:
            path = sf["path"]
            size = sf.get("size", 0)
            line_count = sf.get("content", "").count("\n") + 1 if sf.get("content") else 0
            sections.append(f"- `{path}` ({line_count} lines)")

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
        "A `.bugbot/context.md` file has been committed to this branch "
        "with full source context for the bug. "
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

    Returns None if area is falsy.  The AI sometimes returns verbose
    descriptions; we take only the text before the first comma or
    period to keep the label short and GitHub-friendly.
    """
    if not area:
        return None
    # Take only the first phrase (before comma, period, or semicolon)
    short = area.split(",")[0].split(".")[0].split(";")[0].strip().lower()
    if not short:
        return None
    label = f"area:{short}"
    if len(label) > 50:
        label = label[:50]
    return (label, "6366f1")


def get_bot_label() -> tuple[str, str]:
    """Return the bot-created label (label_name, hex_color)."""
    return ("bot-created", "8b5cf6")


# ------------------------------------------------------------------
# AI Code Fix PR templates (Phase 5)
# ------------------------------------------------------------------


def build_process_log_section(process_log: dict) -> str:
    """Build a collapsible HTML details block for the PR body showing the agentic process log.

    *process_log* is expected to have keys:
    - ``files_explored``: list of file paths explored during fix generation
    - ``rounds``: list of round dicts, each with ``round``, ``files_changed``,
      ``tokens``, and optionally ``lint``, ``self_review``, ``ci``
    - ``total_tokens``: dict with ``input`` and ``output`` counts
    """
    rounds = process_log.get("rounds", [])
    files_explored = process_log.get("files_explored", [])
    total_tokens = process_log.get("total_tokens", {"input": 0, "output": 0})

    total_tok = total_tokens.get("input", 0) + total_tokens.get("output", 0)

    sections = [
        "<details>",
        "<summary>\U0001f916 AI Code Fix Process Log</summary>",
        "",
        f"**Rounds:** {len(rounds)}",
        f"**Files explored:** {len(files_explored)}",
        f"**Total tokens:** {total_tokens.get('input', 0):,} input "
        f"+ {total_tokens.get('output', 0):,} output "
        f"= {total_tok:,} total",
    ]

    for rnd in rounds:
        round_num = rnd.get("round", "?")
        files_changed = rnd.get("files_changed", [])
        files_str = ", ".join(f"`{p}`" for p in files_changed) if files_changed else "None"

        sections.extend([
            "",
            f"### Round {round_num}",
            f"- **Files changed:** {files_str}",
        ])

        # Lint result
        lint = rnd.get("lint")
        if lint is not None:
            if lint.get("skipped"):
                linter_name = lint.get("linter") or "unknown"
                sections.append(f"- **Lint:** \u23ed\ufe0f Skipped ({linter_name})")
            elif lint.get("linter") is None:
                sections.append("- **Lint:** \u23ed\ufe0f Skipped (no linter detected)")
            elif lint.get("passed"):
                sections.append(f"- **Lint:** \u2705 Passed ({lint['linter']})")
            else:
                sections.append(f"- **Lint:** \u274c Failed ({lint['linter']})")

        # Self-review result
        self_review = rnd.get("self_review")
        if self_review is not None:
            if self_review.get("passed"):
                sections.append("- **Self-review:** \u2705 Passed")
            else:
                issues = self_review.get("issues", [])
                issues_text = "; ".join(issues) if issues else "Issues found"
                sections.append(f"- **Self-review:** \u274c {issues_text}")

        # CI result
        ci = rnd.get("ci")
        if ci is not None:
            ci_status = ci.get("status", "unknown")
            if ci_status == "passed":
                sections.append("- **CI:** \u2705 Passed")
            elif ci_status == "failed":
                details = ci.get("details", "")
                sections.append(f"- **CI:** \u274c Failed{' -- ' + details if details else ''}")
            elif ci_status == "no_ci":
                sections.append("- **CI:** \u23ed\ufe0f Skipped (no CI configured)")
            elif ci_status == "timeout":
                sections.append("- **CI:** \u23f1\ufe0f Timeout")
            else:
                sections.append(f"- **CI:** {ci_status}")

    sections.extend([
        "",
        "</details>",
    ])

    return "\n".join(sections)


def build_code_fix_pr_body(
    bug: dict,
    issue_number: int | None = None,
    discord_thread_url: str | None = None,
    process_log: dict | None = None,
    changed_files: dict[str, str] | None = None,
    validation_passed: bool = False,
    developer_notes: list[dict] | None = None,
) -> str:
    """Build the full PR body for an AI-generated code fix PR.

    This is a separate, enhanced version of ``build_pr_body`` designed
    specifically for code fix PRs. The original ``build_pr_body`` is
    preserved for backward compatibility with scaffold PRs.

    Args:
        bug: Bug dict from the database.
        issue_number: GitHub issue number (if an issue exists).
        discord_thread_url: URL to the Discord thread.
        process_log: Process log dict from CodeFixService.
        changed_files: Dict of path -> file content for changed files.
        validation_passed: Whether all quality gates passed.
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

    # Developer Notes section (Phase 6 traceability)
    if developer_notes:
        sections.extend(["", "### Developer Notes"])
        for note in developer_notes:
            author = note.get("author_name", "Unknown")
            content = note.get("content", "")
            timestamp = note.get("created_at", "")
            sections.append(f"- **{author}** ({timestamp}): {content}")

    # Changes Made section
    if changed_files:
        sections.extend(["", "### Changes Made"])
        for path, content in changed_files.items():
            line_count = content.count("\n") + 1 if content else 0
            sections.append(f"- `{path}` ({line_count} lines)")

    # Validation warning
    if not validation_passed:
        rounds_taken = len((process_log or {}).get("rounds", []))
        sections.extend([
            "",
            f"> \u26a0\ufe0f **Note:** AI validation did not fully pass after "
            f"{rounds_taken} round{'s' if rounds_taken != 1 else ''}. "
            f"Please review carefully.",
        ])

    # Process log section
    if process_log:
        sections.extend([
            "",
            build_process_log_section(process_log),
        ])

    # Discord thread link
    if discord_thread_url:
        sections.extend([
            "",
            f"\U0001f517 [Discord Thread]({discord_thread_url})",
        ])

    # Closes issue reference
    if issue_number is not None:
        sections.extend([
            "",
            f"Closes #{issue_number}",
        ])

    sections.extend([
        "",
        "---",
        "> \U0001f916 This fix was generated by PreserveFood BugBot's AI Code Fix engine.",
    ])

    return "\n".join(sections)
