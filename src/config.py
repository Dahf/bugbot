"""Configuration loaded from environment variables."""

import base64
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration from environment variables.

    Required env vars: DISCORD_TOKEN, BUG_CHANNEL_ID, WEBHOOK_SECRET.
    All others have sensible defaults.
    """

    def __init__(self) -> None:
        # Required
        self.DISCORD_TOKEN: str = self._require("DISCORD_TOKEN")
        self.BUG_CHANNEL_ID: int = int(self._require("BUG_CHANNEL_ID"))
        self.WEBHOOK_SECRET: str = self._require("WEBHOOK_SECRET")

        # Optional with defaults
        self.WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8087"))
        self.WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
        self.DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bugs.db")
        self.DEVELOPER_ROLE_NAME: str = os.getenv("DEVELOPER_ROLE_NAME", "Developer")
        self.SIGNATURE_HEADER_NAME: str = os.getenv(
            "SIGNATURE_HEADER_NAME", "X-Webhook-Signature"
        )

        # AI Analysis (Phase 2) -- optional, bot works without these
        self.ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
        self.ANTHROPIC_MODEL: str = os.getenv(
            "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
        )
        self.AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "1024"))

        # GitHub Integration (Phase 3) -- optional, bot works without these
        self.GITHUB_APP_ID: str | None = os.getenv("GITHUB_APP_ID")
        self.GITHUB_PRIVATE_KEY: str | None = self._load_github_private_key()
        self.GITHUB_CLIENT_ID: str | None = os.getenv("GITHUB_CLIENT_ID")
        self.GITHUB_CLIENT_SECRET: str | None = os.getenv("GITHUB_CLIENT_SECRET")
        self.GITHUB_WEBHOOK_SECRET: str | None = os.getenv("GITHUB_WEBHOOK_SECRET")
        self.GITHUB_APP_NAME: str | None = os.getenv("GITHUB_APP_NAME")

        # AI Code Fix (Phase 5) -- optional
        self.ANTHROPIC_CODE_FIX_MODEL: str = os.getenv(
            "ANTHROPIC_CODE_FIX_MODEL", "claude-sonnet-4-5-20250929"
        )
        self.CODE_FIX_MAX_ROUNDS: int = int(
            os.getenv("CODE_FIX_MAX_ROUNDS", "3")
        )
        self.CODE_FIX_MAX_TOKENS: int = int(
            os.getenv("CODE_FIX_MAX_TOKENS", "4096")
        )
        self.CODE_FIX_MAX_FILES: int = int(
            os.getenv("CODE_FIX_MAX_FILES", "15")
        )
        self.CODE_FIX_CI_TIMEOUT: int = int(
            os.getenv("CODE_FIX_CI_TIMEOUT", "300")
        )

        # Code fix mode selection: "anthropic" (default) or "copilot"
        self.CODE_FIX_MODE: str = os.getenv("CODE_FIX_MODE", "anthropic")

        # GitHub PAT for Copilot agent mode (required when CODE_FIX_MODE=copilot)
        self.GITHUB_PAT: str | None = os.getenv("GITHUB_PAT")

        # Copilot session timeout in seconds (default: 1 hour)
        self.COPILOT_SESSION_TIMEOUT: int = int(
            os.getenv("COPILOT_SESSION_TIMEOUT", "3600")
        )

    @property
    def github_configured(self) -> bool:
        """Return True when all required GitHub App credentials are set."""
        return all([
            self.GITHUB_APP_ID,
            self.GITHUB_PRIVATE_KEY,
            self.GITHUB_CLIENT_ID,
            self.GITHUB_CLIENT_SECRET,
        ])

    @property
    def copilot_configured(self) -> bool:
        """Return True when Copilot agent mode is fully configured."""
        return (
            self.CODE_FIX_MODE == "copilot"
            and self.GITHUB_PAT is not None
            and self.github_configured
        )

    @staticmethod
    def _load_github_private_key() -> str | None:
        """Load the GitHub App private key from GITHUB_PRIVATE_KEY env var.

        Expects a base64-encoded PEM string. Returns None if not set.
        """
        key_b64 = os.getenv("GITHUB_PRIVATE_KEY")
        if key_b64:
            try:
                return base64.b64decode(key_b64).decode("utf-8")
            except Exception:
                return key_b64

        return None

    @staticmethod
    def _require(key: str) -> str:
        """Return the value for *key* or raise if missing/empty."""
        value = os.getenv(key)
        if not value:
            raise ValueError(
                f"Missing required environment variable: {key}. "
                f"See .env.example for reference."
            )
        return value
