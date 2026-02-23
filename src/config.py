"""Configuration loaded from environment variables."""

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
