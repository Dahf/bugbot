"""Webhook server cog -- aiohttp web server running alongside the Discord bot."""

import json
import logging
from datetime import datetime, timezone

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands

from src.utils.webhook_auth import validate_webhook_signature

try:
    from githubkit.webhooks import verify as gh_verify_signature
except ImportError:
    gh_verify_signature = None

logger = logging.getLogger(__name__)


class WebhookServer(commands.Cog):
    """Runs an aiohttp web server that receives Supabase and GitHub webhook POSTs.

    Routes:
        POST /webhook/bug-report  -- validate HMAC, store payload, queue for processing
        POST /webhook/chat-report -- validate HMAC, post chat report embed to Discord
        POST /webhook/github      -- validate signature, dispatch to GitHubIntegration cog
        GET  /health              -- liveness check with queue depth
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    async def cog_load(self) -> None:
        """Start the aiohttp web server when the cog is loaded."""
        self._http_session: aiohttp.ClientSession | None = None

        app = web.Application()
        app.router.add_post("/webhook/bug-report", self.handle_webhook)
        app.router.add_post("/webhook/chat-report", self.handle_chat_report)
        app.router.add_post("/webhook/github", self.handle_github_webhook)
        app.router.add_get("/health", self.health_check)
        app.router.add_route(
            "OPTIONS",
            "/api/discord/channels/{channel_id}/messages",
            self.handle_cors_preflight,
        )
        app.router.add_get(
            "/api/discord/channels/{channel_id}/messages",
            self.proxy_discord_messages,
        )

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        host = self.bot.config.WEBHOOK_HOST
        port = self.bot.config.WEBHOOK_PORT
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        logger.info("Webhook server listening on %s:%d", host, port)

    async def cog_unload(self) -> None:
        """Stop the web server and clean up when the cog is unloaded."""
        if self._http_session is not None:
            await self._http_session.close()
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

    async def handle_chat_report(self, request: web.Request) -> web.Response:
        """Receive a chat report webhook, validate HMAC, post embed to Discord."""
        try:
            raw_body = await request.read()

            signature = request.headers.get(
                self.bot.config.SIGNATURE_HEADER_NAME, ""
            )
            if not signature or not validate_webhook_signature(
                raw_body, signature, self.bot.config.WEBHOOK_SECRET
            ):
                logger.warning("Chat report rejected: invalid or missing signature")
                return web.json_response(
                    {"error": "Invalid signature"}, status=401
                )

            try:
                payload = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Chat report rejected: invalid JSON -- %s", exc)
                return web.json_response(
                    {"error": "Invalid JSON body"}, status=400
                )

            channel_id = self.bot.config.CHAT_REPORT_CHANNEL_ID
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                logger.error("Chat report channel %d not found", channel_id)
                return web.json_response(
                    {"error": "Channel not configured"}, status=500
                )

            embed = self._build_chat_report_embed(payload)
            await channel.send(embed=embed)

            logger.info(
                "Posted chat report %s to channel %d",
                payload.get("supabase_id"),
                channel_id,
            )
            return web.json_response(
                {"status": "received", "supabase_id": payload.get("supabase_id")},
                status=200,
            )

        except Exception:
            logger.exception("Unexpected error handling chat report")
            return web.json_response(
                {"error": "Internal server error"}, status=500
            )

    @staticmethod
    def _build_chat_report_embed(payload: dict) -> discord.Embed:
        """Build a Discord embed from a chat report payload."""
        reason = payload.get("reason") or "No reason provided"
        embed = discord.Embed(
            title=f"Chat Report -- {reason}",
            description=payload.get("note") or None,
            color=discord.Color.orange(),
        )

        message_text = payload.get("message")
        if message_text:
            truncated = message_text if len(message_text) <= 1024 else message_text[:1021] + "..."
            embed.add_field(name="Reported Message", value=truncated, inline=False)

        reporter_name = payload.get("reporter_name") or "Unknown"
        reporter_email = payload.get("reporter_email") or "n/a"
        embed.add_field(
            name="Reporter",
            value=f"{reporter_name} ({reporter_email})",
            inline=False,
        )

        if payload.get("user_id"):
            embed.add_field(name="Reported User ID", value=str(payload["user_id"]), inline=True)
        if payload.get("meal_id"):
            embed.add_field(name="Meal ID", value=str(payload["meal_id"]), inline=True)
        if payload.get("supabase_id"):
            embed.add_field(name="Report ID", value=str(payload["supabase_id"]), inline=False)

        created_at = payload.get("created_at")
        if created_at:
            try:
                embed.timestamp = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass
        else:
            embed.timestamp = datetime.now(timezone.utc)

        return embed

    async def handle_github_webhook(
        self, request: web.Request
    ) -> web.Response:
        """Receive a GitHub webhook, validate signature, dispatch to cog.

        Uses GITHUB_WEBHOOK_SECRET (separate from the Supabase WEBHOOK_SECRET
        per Pitfall 5 in RESEARCH.md).
        """
        try:
            raw_body = await request.read()

            # 1. Check GITHUB_WEBHOOK_SECRET is configured
            gh_secret = getattr(self.bot.config, "GITHUB_WEBHOOK_SECRET", None)
            if not gh_secret:
                logger.warning("GitHub webhook received but GITHUB_WEBHOOK_SECRET not set")
                return web.json_response(
                    {"error": "GitHub webhook not configured"}, status=500
                )

            # 2. Validate signature
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not signature:
                logger.warning("GitHub webhook rejected: missing signature header")
                return web.json_response(
                    {"error": "Missing signature"}, status=401
                )

            if gh_verify_signature is None:
                logger.error("githubkit.webhooks.verify not available")
                return web.json_response(
                    {"error": "Server misconfigured"}, status=500
                )

            try:
                gh_verify_signature(gh_secret, raw_body, signature)
            except Exception:
                logger.warning("GitHub webhook rejected: invalid signature")
                return web.json_response(
                    {"error": "Invalid signature"}, status=401
                )

            # 3. Parse event
            event_name = request.headers.get("X-GitHub-Event", "unknown")
            try:
                payload = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("GitHub webhook: invalid JSON -- %s", exc)
                return web.json_response(
                    {"error": "Invalid JSON body"}, status=400
                )

            # 4. Dispatch to GitHubIntegration cog
            github_cog = self.bot.get_cog("GitHubIntegration")
            if github_cog is not None:
                try:
                    await github_cog.handle_github_event(event_name, payload)
                except Exception:
                    logger.exception(
                        "Error handling GitHub %s event", event_name
                    )
            else:
                logger.debug(
                    "GitHubIntegration cog not loaded, ignoring %s event",
                    event_name,
                )

            return web.json_response({"status": "ok"}, status=200)

        except Exception:
            logger.exception("Unexpected error handling GitHub webhook")
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

    # ------------------------------------------------------------------
    # Discord API proxy
    # ------------------------------------------------------------------

    def _cors_headers(self) -> dict[str, str]:
        origin = self.bot.config.PROXY_ALLOWED_ORIGIN
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, X-API-Key",
        }

    async def handle_cors_preflight(
        self, request: web.Request
    ) -> web.Response:
        """Respond to CORS preflight (OPTIONS) requests."""
        return web.Response(status=204, headers=self._cors_headers())

    async def proxy_discord_messages(
        self, request: web.Request
    ) -> web.Response:
        """Proxy GET /api/discord/channels/{channel_id}/messages to Discord REST API.

        Optional auth: set PROXY_API_KEY in .env, then pass it as
        ``?api_key=<key>`` query parameter or ``X-API-Key`` header.
        """
        try:
            # --- API key check (skip if PROXY_API_KEY is not configured) ---
            expected_key = self.bot.config.PROXY_API_KEY
            if expected_key:
                provided_key = (
                    request.query.get("api_key")
                    or request.headers.get("X-API-Key", "")
                )
                if provided_key != expected_key:
                    return web.json_response(
                        {"error": "Unauthorized"},
                        status=401,
                        headers=self._cors_headers(),
                    )

            channel_id = request.match_info["channel_id"]
            limit = request.query.get("limit", "100")

            # Lazy-init a shared client session
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()

            discord_url = (
                f"https://discord.com/api/v10/channels/{channel_id}/messages"
            )
            headers = {
                "Authorization": f"Bot {self.bot.config.DISCORD_TOKEN}",
            }

            async with self._http_session.get(
                discord_url, headers=headers, params={"limit": limit}
            ) as resp:
                body = await resp.read()
                return web.Response(
                    body=body,
                    status=resp.status,
                    content_type="application/json",
                    headers=self._cors_headers(),
                )

        except Exception:
            logger.exception("Error proxying Discord messages")
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
                headers=self._cors_headers(),
            )


async def setup(bot: commands.Bot) -> None:
    """Entry point for discord.py extension loading."""
    await bot.add_cog(WebhookServer(bot))
