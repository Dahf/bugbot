"""BugBot -- Discord bot for receiving and managing bug reports."""

import asyncio
import logging
import os

import discord
from discord.ext import commands

from src.config import Config
from src.models.bug import BugRepository
from src.models.database import setup_database, close_database

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

        # Load cog extensions (wrap in try/except -- cogs may not exist yet)
        cog_extensions = [
            "src.cogs.webhook",
            "src.cogs.bug_reports",
        ]
        for ext in cog_extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except commands.ExtensionNotFound:
                logger.warning("Extension not found (will be added later): %s", ext)
            except Exception as exc:
                logger.error("Failed to load extension %s: %s", ext, exc)

        # TODO: Register DynamicItems for persistent buttons (added in Plan 01-02)

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
