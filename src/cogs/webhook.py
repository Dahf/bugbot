"""Webhook server cog -- aiohttp web server running alongside the Discord bot."""

import json
import logging

from aiohttp import web
from discord.ext import commands

from src.utils.webhook_auth import validate_webhook_signature

logger = logging.getLogger(__name__)


class WebhookServer(commands.Cog):
    """Runs an aiohttp web server that receives Supabase webhook POSTs.

    Routes:
        POST /webhook/bug-report -- validate HMAC, store payload, queue for processing
        GET  /health             -- liveness check with queue depth
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    async def cog_load(self) -> None:
        """Start the aiohttp web server when the cog is loaded."""
        app = web.Application()
        app.router.add_post("/webhook/bug-report", self.handle_webhook)
        app.router.add_get("/health", self.health_check)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        host = self.bot.config.WEBHOOK_HOST
        port = self.bot.config.WEBHOOK_PORT
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        logger.info("Webhook server listening on %s:%d", host, port)

    async def cog_unload(self) -> None:
        """Stop the web server and clean up when the cog is unloaded."""
        if self.site is not None:
            await self.site.stop()
            logger.info("Webhook server TCPSite stopped")
        if self.runner is not None:
            await self.runner.cleanup()
            logger.info("Webhook server AppRunner cleaned up")

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Receive a bug report webhook, validate HMAC, store, and queue.

        Returns 200 immediately after storing -- processing happens async
        via the BugReports cog's queue consumer (store-then-process).
        """
        try:
            # Read raw body for HMAC validation
            raw_body = await request.read()

            # Validate HMAC signature
            signature = request.headers.get(
                self.bot.config.SIGNATURE_HEADER_NAME, ""
            )
            if not signature or not validate_webhook_signature(
                raw_body, signature, self.bot.config.WEBHOOK_SECRET
            ):
                logger.warning("Webhook rejected: invalid or missing signature")
                return web.json_response(
                    {"error": "Invalid signature"}, status=401
                )

            # Parse JSON body
            try:
                payload = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Webhook rejected: invalid JSON -- %s", exc)
                return web.json_response(
                    {"error": "Invalid JSON body"}, status=400
                )

            # Store immediately (store-then-process per FOUND-08)
            hash_id = await self.bot.bug_repo.store_raw_report(payload)
            logger.info("Stored bug report %s, queuing for processing (screenshot_url=%r)", hash_id, payload.get("screenshot_url"))

            # Queue for async Discord processing
            await self.bot.processing_queue.put(hash_id)

            return web.json_response(
                {"status": "received", "bug_id": hash_id}, status=200
            )

        except Exception:
            logger.exception("Unexpected error handling webhook")
            return web.json_response(
                {"error": "Internal server error"}, status=500
            )

    async def health_check(self, request: web.Request) -> web.Response:
        """Liveness endpoint returning server status and queue depth."""
        return web.json_response(
            {
                "status": "ok",
                "queue_size": self.bot.processing_queue.qsize(),
            }
        )


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(WebhookServer(bot))
