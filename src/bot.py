"""BugBot -- Discord bot for receiving and managing bug reports."""

import asyncio
import logging
import os

import discord
from discord.ext import commands

from src.config import Config
from src.models.bug import BugRepository
from src.models.database import setup_database, close_database
from src.models.github_config import GitHubConfigRepository
from src.services.ai_analysis import AIAnalysisService
from src.services.github_service import GitHubService
from src.views.bug_buttons import BugActionButton

logger = logging.getLogger(__name__)


class BugBot(commands.Bot):
    """Discord bot that receives Supabase webhook bug reports and manages them."""

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        # message_content intent NOT needed -- we use buttons/interactions only
        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.db = None
        self.bug_repo: BugRepository | None = None
        self.ai_service: AIAnalysisService | None = None
        self.github_service: GitHubService | None = None
        self.github_config_repo: GitHubConfigRepository | None = None
        self.processing_queue: asyncio.Queue = asyncio.Queue()

    async def setup_hook(self) -> None:
        """Async initialisation that runs before the bot connects to Discord."""
        # Ensure data directory exists for SQLite
        db_dir = os.path.dirname(self.config.DATABASE_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        # Initialise database and repository
        self.db = await setup_database(self.config.DATABASE_PATH)
        self.bug_repo = BugRepository(self.db)
        logger.info("Database initialised at %s", self.config.DATABASE_PATH)

        # Initialize AI analysis service (optional -- bot works without it)
        if self.config.ANTHROPIC_API_KEY:
            self.ai_service = AIAnalysisService(
                api_key=self.config.ANTHROPIC_API_KEY,
                model=self.config.ANTHROPIC_MODEL,
                max_tokens=self.config.AI_MAX_TOKENS,
            )
            logger.info(
                "AI analysis service initialized (model: %s)",
                self.config.ANTHROPIC_MODEL,
            )
        else:
            logger.warning("ANTHROPIC_API_KEY not set -- AI analysis disabled")

        # Initialize GitHub service (optional -- bot works without it)
        if self.config.github_configured:
            self.github_service = GitHubService(
                app_id=self.config.GITHUB_APP_ID,
                private_key=self.config.GITHUB_PRIVATE_KEY,
                client_id=self.config.GITHUB_CLIENT_ID,
                client_secret=self.config.GITHUB_CLIENT_SECRET,
            )
            self.github_config_repo = GitHubConfigRepository(self.db)
            logger.info("GitHub integration initialized")
        else:
            logger.warning("GitHub App not configured -- GitHub integration disabled")

        # Load cog extensions (wrap in try/except -- cogs may not exist yet)
        cog_extensions = [
            "src.cogs.webhook",
            "src.cogs.bug_reports",
            "src.cogs.ai_analysis",
            "src.cogs.github_integration",
        ]
        for ext in cog_extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except commands.ExtensionNotFound:
                logger.warning("Extension not found (will be added later): %s", ext)
            except Exception as exc:
                logger.error("Failed to load extension %s: %s", ext, exc)

        # Register DynamicItems for persistent buttons (FOUND-06)
        # Must happen in setup_hook before bot connects so buttons survive restarts
        self.add_dynamic_items(BugActionButton)
        logger.info("Registered BugActionButton DynamicItem")

        # Sync app commands (slash commands) with Discord
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d app command(s)", len(synced))
        except Exception as exc:
            logger.error("Failed to sync app commands: %s", exc)

    async def on_ready(self) -> None:
        """Called when the bot has connected to Discord."""
        logger.info(
            "Logged in as %s (ID: %s) | Guilds: %d | Channel: %s",
            self.user,
            self.user.id,
            len(self.guilds),
            self.config.BUG_CHANNEL_ID,
        )

    async def close(self) -> None:
        """Clean up resources before shutting down."""
        if self.github_service is not None:
            await self.github_service.close()
            logger.info("GitHub service closed")
        if self.db is not None:
            await close_database(self.db)
            logger.info("Database connection closed")
        await super().close()


def main() -> None:
    """Entry point for the bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = Config()
    bot = BugBot(config)
    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
