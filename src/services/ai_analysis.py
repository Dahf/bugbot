"""AI analysis service using Claude API for bug report triage."""

import json
import logging

from anthropic import AsyncAnthropic

from src.utils.embeds import _parse_json_field

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# System prompt with structured JSON output and P1-P4 scoring rubric
# -----------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior software engineer triaging bug reports for a mobile application.

Analyze the bug report and respond with ONLY a JSON object (no markdown, no code fences) with these exact fields:

{
  "root_cause": "A detailed paragraph explaining the likely root cause, your reasoning, and what is happening technically.",
  "affected_area": "The specific code area, module, or feature most likely affected (e.g., 'Authentication module', 'Camera capture flow').",
  "severity": "One of: critical, high, medium, low",
  "suggested_fix": "A brief 1-2 sentence hint about the recommended fix approach.",
  "priority": "One of: P1, P2, P3, P4",
  "priority_reasoning": "Brief explanation of the priority score (e.g., 'P2: high severity crash but low frequency affecting <1% of users')."
}

Priority scoring rubric:
- P1 (Critical): App crashes, data loss, security vulnerabilities, or issues affecting >50% of users. Drop everything.
- P2 (High): Major feature broken, significant UX degradation, or moderate user impact. This sprint.
- P3 (Medium): Minor feature issues, cosmetic bugs with workarounds, low user impact. Soon.
- P4 (Low): Edge cases, minor polish, nice-to-haves. Backlog.

Weigh multiple factors: severity of the bug itself, estimated user impact/reach, and likely frequency of occurrence. No single factor should dominate."""

# Required keys that must appear in every valid analysis response
_REQUIRED_KEYS = frozenset(
    {"root_cause", "affected_area", "severity", "suggested_fix", "priority", "priority_reasoning"}
)

_VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}


class AIAnalysisService:
    """Encapsulates Claude API interactions for bug analysis."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
    ) -> None:
        self.client = AsyncAnthropic(
            api_key=api_key,
            timeout=60.0,
            max_retries=3,
        )
        self.model = model
        self.max_tokens = max_tokens

    async def analyze_bug(self, bug: dict) -> dict:
        """Analyze a bug report and return structured results.

        Returns a dict with keys: root_cause, affected_area, severity,
        suggested_fix, priority, priority_reasoning, and usage.

        Raises ``anthropic.APIError`` subclasses on API failure (propagated
        to the caller for UX handling).  Raises ``ValueError`` if the
        response cannot be parsed as valid JSON.
        """
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(bug)

        message = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        text = message.content[0].text
        result = self._parse_response(text)

        # Attach token usage
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        total_tokens = input_tokens + output_tokens
        result["usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

        logger.info(
            "AI analysis complete: %d tokens (%d in, %d out)",
            total_tokens,
            input_tokens,
            output_tokens,
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Return the system prompt for bug analysis."""
        return SYSTEM_PROMPT

    def _build_user_message(self, bug: dict) -> str:
        """Build the user message containing all available bug details."""
        hash_id = bug.get("hash_id", "unknown")
        title = bug.get("title") or "N/A"
        description = bug.get("description") or "N/A"
        severity = bug.get("severity") or "N/A"
        app_version = bug.get("app_version") or "N/A"
        steps = bug.get("steps_to_reproduce") or "N/A"

        # Format device_info (handles both JSON string and dict forms)
        device_raw = bug.get("device_info")
        device_parsed = _parse_json_field(device_raw)
        if isinstance(device_parsed, dict):
            platform = device_parsed.get("platform", "?")
            os_version = device_parsed.get("osVersion", "?")
            device_display = f"{platform} {os_version}"
        elif device_parsed:
            device_display = str(device_parsed)
        else:
            device_display = "N/A"

        # Format console_logs (handles both JSON string and list forms)
        logs_raw = bug.get("console_logs")
        logs_parsed = _parse_json_field(logs_raw)
        if isinstance(logs_parsed, list):
            log_lines = []
            for entry in logs_parsed:
                if isinstance(entry, dict):
                    level = entry.get("level", "info")
                    msg = entry.get("message", "")
                    log_lines.append(f"[{level}] {msg}")
                else:
                    log_lines.append(str(entry))
            logs_display = "\n".join(log_lines) if log_lines else "None available"
        elif logs_parsed:
            logs_display = str(logs_parsed)
        else:
            logs_display = "None available"

        return (
            f"Bug Report #{hash_id}\n"
            f"\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Severity (user-reported): {severity}\n"
            f"Device: {device_display}\n"
            f"App Version: {app_version}\n"
            f"Steps to Reproduce: {steps}\n"
            f"\n"
            f"Console Logs:\n"
            f"{logs_display}"
        )

    def _parse_response(self, text: str) -> dict:
        """Parse the Claude response text into a validated dict.

        Handles both clean JSON and markdown-wrapped JSON (code fences).
        Normalizes severity to lowercase and priority to uppercase.
        """
        # First try direct parse
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try stripping markdown code fences
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                try:
                    parsed = json.loads(text[first_brace : last_brace + 1])
                except json.JSONDecodeError:
                    logger.error("Failed to parse AI response: %s", text)
                    raise ValueError("Failed to parse AI response as JSON")
            else:
                logger.error("Failed to parse AI response: %s", text)
                raise ValueError("Failed to parse AI response as JSON")

        # Validate required keys
        missing = _REQUIRED_KEYS - set(parsed.keys())
        if missing:
            logger.error("AI response missing keys %s: %s", missing, text)
            raise ValueError(f"AI response missing required keys: {missing}")

        # Normalize severity to lowercase
        parsed["severity"] = str(parsed["severity"]).lower()

        # Normalize priority to uppercase
        parsed["priority"] = str(parsed["priority"]).upper()

        # Validate priority value
        if parsed["priority"] not in _VALID_PRIORITIES:
            logger.warning(
                "AI returned invalid priority '%s', defaulting to P3",
                parsed["priority"],
            )
            parsed["priority"] = "P3"

        return parsed
